"""Drawing inventory (DXF full, DWG experimental) and cross-check against generated rows.

The drawing is used for validation only: it never changes a generated value or status.
"""

from __future__ import annotations

import re
from pathlib import Path

from .builder import OlmResult
from .model import Issue

DEFAULTS = {
    # Block attribute tags of address points in the SpatialNet drawing export (DXF only).
    "address_number_tag": "STREET_NUMBER",
    "address_street_tag": "STREET_NAME",
    "closure_regex": r"(?<![A-Z0-9-])[A-Z]{2,5}-\d{4,6}G?(?![A-Z0-9])",
    "cable_regex": r"[A-Z]{2,5}-[A-Z0-9-]+ TO [A-Z]{2,5}-[A-Z0-9 -]+? FC\d{3}",
    "tap_regex": r"[A-Z]{2,5}-R\d*-(?:C-)?\d+ [A-Z0-9 .-]+",
}


def _patterns(cfg: dict):
    d = {**DEFAULTS, **cfg.get("drawing", {})}
    return re.compile(d["closure_regex"]), re.compile(d["cable_regex"]), re.compile(d["tap_regex"])


def _dxf_texts(path: Path, cfg: dict) -> tuple[list[str], dict]:
    from ezdxf import recover  # optional dependency
    d = {**DEFAULTS, **cfg.get("drawing", {})}
    doc, auditor = recover.readfile(str(path))
    texts, stats = [], {"entities": 0, "layers": len(doc.layers), "blocks": len(doc.blocks), "addresses": set()}
    for layout in list(doc.layouts) + list(doc.blocks):
        for e in layout:
            stats["entities"] += 1
            t = e.dxftype()
            if t in ("TEXT", "ATTRIB", "ATTDEF"):
                texts.append(e.dxf.get("text", ""))
            elif t == "MTEXT":
                texts.append(e.plain_text())
            elif t == "INSERT":
                texts.append(e.dxf.name)
                tags = {}
                for a in e.attribs:
                    texts.append(a.dxf.get("text", ""))
                    tags[a.dxf.get("tag", "").upper()] = " ".join(str(a.dxf.get("text", "")).split())
                num, street = tags.get(d["address_number_tag"]), tags.get(d["address_street_tag"])
                if num and street:
                    stats["addresses"].add(f"{num} {street}".upper())
            elif t == "MULTILEADER":
                try:
                    texts.append(e.context.mtext.default_content)
                except AttributeError:
                    pass
    stats["errors_repaired"] = len(auditor.errors) if auditor else 0
    return texts, stats


def read_drawing_inventory(path: Path, cfg: dict):
    """Returns (inventory dict or None, issues)."""
    issues: list[Issue] = []
    if not path.exists():
        return None, [Issue("ERROR", "DRAWING_MISSING", f"Drawing not found: {path}")]
    suffix = path.suffix.lower()
    try:
        if suffix == ".dxf":
            try:
                texts, stats = _dxf_texts(path, cfg)
            except ImportError:
                return None, [Issue("ERROR", "DRAWING_NO_EZDXF", "DXF cross-check needs the 'ezdxf' package "
                                    "(pip install ezdxf)")]
            method = f"DXF text/attribute read ({stats['entities']} entities)"
            complete = True
            addresses = stats["addresses"]
        elif suffix == ".dwg":
            from .dwg_container import DwgContainer
            dwg = DwgContainer(path)
            texts = dwg.text_strings()
            method = f"DWG {dwg.version} built-in string scan (experimental, partial)"
            complete = False
            addresses = None  # address points need attribute pairing: DXF only
            issues.append(Issue("INFO", "DRAWING_DWG_PARTIAL",
                                "DWG read with the built-in string scanner: identifiers found are reliable, but "
                                "absence is not evidence. Export a DXF for a complete cross-check.",
                                source=path.name))
        else:
            return None, [Issue("ERROR", "DRAWING_UNSUPPORTED", f"Unsupported drawing type {suffix}; use .dxf or .dwg")]
    except Exception as exc:
        return None, [Issue("ERROR", "DRAWING_UNREADABLE", f"{path.name}: {exc}")]
    c_re, k_re, t_re = _patterns(cfg)
    closures, cables, taps = set(), set(), set()
    for t in texts:
        t = " ".join(str(t).split())
        closures.update(c_re.findall(t))
        cables.update(m.strip() for m in k_re.findall(t))
        taps.update(m.strip() for m in t_re.findall(t))
    return {"source": path.name, "method": method, "complete": complete, "closures": closures,
            "cables": cables, "taps": taps, "addresses": addresses}, issues


def address_coverage(results: list[OlmResult], inv: dict):
    """Premises drawn as address points but served by no fibre in any generated list (DXF only)."""
    if not inv or inv.get("addresses") is None:
        return [], []
    served = {" ".join(str(r.value("address")).split()).upper() for res in results for r in res.rows
              if r.kind == "subscriber" and r.value("address")}
    drawn = inv["addresses"]
    rows = [{"check": "Address point not in any list", "identifier": a, "found": "drawing only"}
            for a in sorted(drawn - served)]
    rows += [{"check": "Listed address without address point", "identifier": a, "found": "list only"}
             for a in sorted(served - drawn)]
    issue = Issue("INFO" if not (drawn - served) else "WARNING", "DRAWING_ADDRESS_COVERAGE",
                  f"{len(drawn & served)}/{len(drawn)} drawn address points are served in the generated list(s); "
                  f"{len(drawn - served)} drawn but not served, {len(served - drawn)} served but not drawn "
                  f"(premises outside these OLMs, or naming differences)")
    return rows, [issue]


def crosscheck(res: OlmResult, inv: dict):
    rows, issues = [], []
    sev = "WARNING" if inv["complete"] else "INFO"
    checks = [("Hub closure", {res.hub} if res.hub else set(), inv["closures"]),
              ("Section cable", {c for c, _, _ in res.sections}, inv["cables"]),
              ("Fiber Splice closure", {r.value("fiber_splice") for r in res.rows if r.value("fiber_splice")},
               inv["closures"])]
    for label, ids, pool in checks:
        found = 0
        for ident in sorted(ids):
            ok = ident in pool
            found += ok
            rows.append({"check": label, "identifier": ident, "found": "yes" if ok else "no"})
        if ids:
            missing = len(ids) - found
            issues.append(Issue("INFO" if not missing else sev, "DRAWING_COVERAGE",
                                f"{label}: {found}/{len(ids)} identifiers found in drawing {inv['source']} "
                                f"({inv['method']})" + ("" if inv["complete"] or not missing else
                                                        " - absence not conclusive with DWG scan"), res.olm))
    return rows, issues

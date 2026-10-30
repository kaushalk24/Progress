"""Drawing inventory (identifiers in the drawing) and cross-check against generated rows.

The inventory only cross-checks; it never changes a value. Fiber Splice resolution from the drawing
is in drawing_splice.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from .builder import OlmResult
from .design import address_text
from .model import Issue

DEFAULTS = {
    # Block attribute tags of address points in the SpatialNet drawing export (DXF only).
    "address_tags": [["STREET_NUMBER", "STREET_NAME"], ["BUILDING_ADDRESS", "BUILDING_NAME"]],
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
                addr = address_text(tags, d)
                if addr:
                    stats["addresses"].add(addr)
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
            try:
                from .design import dwg_entities
                inserts, _lines, texts, meta = dwg_entities(path)
                if meta["objects"] and meta["decode_errors"] > 0.01 * meta["objects"]:
                    raise ValueError(f"{meta['decode_errors']} objects not decoded")
                d = {**DEFAULTS, **cfg.get("drawing", {})}
                texts = texts + [v for ins in inserts for v in ins.attribs.values()]
                addresses = {a for ins in inserts if (a := address_text(ins.attribs, d))}
                method = f"{meta['method']} ({meta['objects']} objects)"
                complete = True
            except Exception as exc:  # unsupported version / damaged objects: fall back to the string scan
                from .dwg_container import DwgContainer
                dwg = DwgContainer(path)
                texts = dwg.text_strings()
                method = f"DWG {dwg.version} built-in string scan (partial)"
                complete = False
                addresses = None
                issues.append(Issue("INFO", "DRAWING_DWG_PARTIAL",
                                    f"DWG objects could not be decoded ({exc}); identifiers were read with the string "
                                    f"scanner: those found are reliable, but absence is not evidence. Export a DXF "
                                    f"for a complete cross-check.", source=path.name))
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


def _address_key(text: str):
    from .design import split_address
    num, core = split_address(text)
    return (num, core) if num else None


def address_coverage(results: list[OlmResult], inv: dict):
    """Premises drawn as address points but served by no fibre in any generated list, and listed
    addresses without an address point. Compared on house number + street name core (the drawing
    usually omits the street type)."""
    if not inv or inv.get("addresses") is None:
        return [], []
    served_raw = {" ".join(str(r.value("address")).split()).upper() for res in results for r in res.rows
                  if r.kind == "subscriber" and r.value("address")}
    drawn_raw = inv["addresses"]
    from .design import streets_match
    served = {k: a for a in sorted(served_raw) if (k := _address_key(a))}
    drawn = {k: a for a in sorted(drawn_raw) if (k := _address_key(a))}
    by_num = {}
    for k in drawn:
        by_num.setdefault(k[0], []).append(k)
    pairs = {(s, d) for s in served for d in by_num.get(s[0], []) if streets_match(s[1], d[1])}
    hit_s, hit_d = {s for s, _ in pairs}, {d for _, d in pairs}
    rows = [{"check": "Address point not in any list", "identifier": drawn[k], "found": "drawing only"}
            for k in sorted(set(drawn) - hit_d)]
    rows += [{"check": "Listed address without address point", "identifier": served[k], "found": "list only"}
             for k in sorted(set(served) - hit_s)]
    rows += [{"check": "Listed address without a house number", "identifier": a, "found": "not comparable"}
             for a in sorted(x for x in served_raw if not _address_key(x))]
    n_drawn_only, n_list_only = len(set(drawn) - hit_d), len(set(served) - hit_s)
    issue = Issue("INFO" if not n_drawn_only else "WARNING", "DRAWING_ADDRESS_COVERAGE",
                  f"{len(hit_d)}/{len(drawn)} drawn address points are served in the generated list(s); "
                  f"{n_drawn_only} drawn but not served, {n_list_only} listed but not drawn "
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

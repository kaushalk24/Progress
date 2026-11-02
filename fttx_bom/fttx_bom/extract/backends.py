"""CAD extraction backends -> normalized Drawing.

* DWG: converted with LibreDWG (WebAssembly build, tools/dwg2json.mjs) to a
  slim JSON file, cached next to the output so repeated runs are fast.
* DXF: read with ezdxf (use this when the DWG was exported from AutoCAD with
  DXFOUT, or converted with the ODA File Converter).
* JSON: a previously produced slim JSON (for tests / offline reruns).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from .model import Drawing, Insert, Leader, Polyline, Text
from .proxy import proxy_polylines

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"

# LibreDWG error bit flags (dwg.h). Values >= 128 are critical.
LIBREDWG_ERRORS = {
    1: "WRONGCRC",
    2: "NOTYETSUPPORTED",
    4: "UNHANDLEDCLASS",
    8: "INVALIDTYPE",
    16: "INVALIDHANDLE",
    32: "INVALIDEED",
    64: "VALUEOUTOFBOUNDS",
    128: "CLASSESNOTFOUND",
    256: "SECTIONNOTFOUND",
    512: "PAGENOTFOUND",
    1024: "INTERNALERROR",
    2048: "INVALIDDWG",
    4096: "IOERROR",
    8192: "OUTOFMEM",
}


class ExtractionError(RuntimeError):
    pass


def _decode_libredwg_code(code: int) -> str:
    return "|".join(name for bit, name in LIBREDWG_ERRORS.items() if code & bit) or "none"


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def dwg_to_json(dwg: Path, cache_dir: Path) -> tuple[Path, list[str]]:
    """Run the LibreDWG converter (cached by file hash). Returns (json path, warnings)."""
    from ..paths import node_exe

    node = node_exe()
    if not node:
        raise ExtractionError("Node.js is required to read DWG files (or supply a DXF export instead).")
    if not (TOOLS_DIR / "node_modules" / "@mlightcad" / "libredwg-web").exists():
        raise ExtractionError(
            f"DWG reader not installed. Run:  cd {TOOLS_DIR} && npm install --ignore-scripts"
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    # the key includes the converter script, so a converter fix re-reads cached drawings
    out = cache_dir / f"{dwg.stem}.{_file_hash(dwg)}.{_file_hash(TOOLS_DIR / 'dwg2json.mjs')[:8]}.dwg.json"
    log = out.with_suffix(".log")
    if not out.exists():
        proc = subprocess.run(
            [node, str(TOOLS_DIR / "dwg2json.mjs"), str(dwg), str(out)],
            capture_output=True,
            text=True,
            timeout=900,
        )
        log.write_text(proc.stdout + proc.stderr, encoding="utf-8")
        if proc.returncode != 0 or not out.exists():
            raise ExtractionError(f"DWG conversion failed for {dwg}:\n{proc.stderr[-2000:]}")
    warnings = []
    for line in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
        if "error code" in line:
            try:
                code = int(line.rsplit(":", 1)[1])
            except ValueError:
                code = -1
            severity = "CRITICAL" if code >= 128 else "non-critical"
            warnings.append(f"LibreDWG reported {severity} read status {code} ({_decode_libredwg_code(code)})")
    return out, warnings


def load_slim_json(path: Path, warnings: list[str] | None = None) -> Drawing:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    d = Drawing(source=data.get("source", Path(path).name), backend=data.get("backend", "json"))
    d.census = Counter(data.get("census", {}))
    d.block_census = data.get("blockCensus", {})
    d.header = data.get("header", {})
    d.warnings = list(warnings or [])
    for e in data["entities"]:
        t = e["t"]
        if t == "INSERT":
            attribs = {}
            for tag, val, _layer in e.get("a", []):
                attribs[tag] = val or ""
            d.inserts.append(Insert(e["h"], e.get("n", ""), e["l"], tuple(e["p"]), e.get("r", 0.0), e.get("sx", 1.0), attribs))
        elif t in ("LWPOLYLINE", "POLYLINE", "POLYLINE2D"):
            pts = [(v[0], v[1]) for v in e.get("v", [])]
            d.polylines.append(Polyline(e["h"], e["l"], pts, bool(e.get("f", 0) & 1), "LWPOLYLINE"))
        elif t == "LINE":
            d.polylines.append(Polyline(e["h"], e["l"], [tuple(p) for p in e["v"]], False, "LINE"))
        elif t in ("TEXT", "MTEXT"):
            d.texts.append(Text(e["h"], e["l"], e.get("s") or "", tuple(e["p"]) if e.get("p") else None, t))
        elif t == "MULTILEADER":
            d.texts.append(Text(e["h"], e["l"], e.get("s") or "", None, "MLEADER"))
        elif t == "LEADER":
            d.leaders.append(Leader(e["h"], e["l"], [tuple(p) for p in e.get("v", []) if p]))
        elif t == "ACAD_PROXY_ENTITY":
            try:
                polys = proxy_polylines(bytes.fromhex(e.get("g", "")))
            except Exception as exc:  # malformed proxy graphics must not be silently lost
                d.warnings.append(f"proxy {e['h']} on {e['l']}: graphics decode failed ({exc})")
                continue
            if not polys:
                d.warnings.append(f"proxy {e['h']} on {e['l']}: no polygon geometry in proxy graphics")
            for pts, _closed in polys:
                d.polylines.append(Polyline(e["h"], e["l"], pts, True, "PROXY"))
    return d


def load_dxf(path: Path) -> Drawing:
    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("ezdxf is required to read DXF files (pip install ezdxf)") from exc
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    d = Drawing(source=Path(path).name, backend=f"ezdxf@{ezdxf.__version__}")
    d.header = {"INSUNITS": doc.header.get("$INSUNITS")}
    for e in msp:
        t = e.dxftype()
        d.census[t] += 1
        layer = e.dxf.get("layer", "0")
        h = e.dxf.handle
        if t == "INSERT":
            attribs = {a.dxf.tag: a.dxf.text for a in e.attribs}
            d.census["ATTRIB"] += len(e.attribs)
            p = e.dxf.insert
            d.inserts.append(Insert(h, e.dxf.name, layer, (p.x, p.y), e.dxf.get("rotation", 0.0), e.dxf.get("xscale", 1.0), attribs))
        elif t == "LWPOLYLINE":
            pts = [(x, y) for x, y, *_ in e.get_points("xy")]
            d.polylines.append(Polyline(h, layer, pts, e.closed, "LWPOLYLINE"))
        elif t == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            d.polylines.append(Polyline(h, layer, pts, e.is_closed, "LWPOLYLINE"))
        elif t == "LINE":
            s, en = e.dxf.start, e.dxf.end
            d.polylines.append(Polyline(h, layer, [(s.x, s.y), (en.x, en.y)], False, "LINE"))
        elif t == "TEXT":
            p = e.dxf.insert
            d.texts.append(Text(h, layer, e.dxf.text, (p.x, p.y), "TEXT"))
        elif t == "MTEXT":
            p = e.dxf.insert
            d.texts.append(Text(h, layer, e.plain_text(), (p.x, p.y), "MTEXT"))
        elif t == "MULTILEADER":
            txt = ""
            try:
                txt = e.context.mtext.default_content if e.context.mtext else ""
            except AttributeError:
                pass
            d.texts.append(Text(h, layer, txt, None, "MLEADER"))
        elif t == "LEADER":
            d.leaders.append(Leader(h, layer, [(v.x, v.y) for v in e.vertices]))
        elif t == "ACAD_PROXY_ENTITY":
            data = getattr(e, "proxy_graphic", None) or b""
            for pts, _closed in proxy_polylines(bytes(data)):
                d.polylines.append(Polyline(h, layer, pts, True, "PROXY"))
    for blk in doc.blocks:
        d.block_census[blk.name] = dict(Counter(x.dxftype() for x in blk))
    return d


def load_drawing(path: str | Path, cache_dir: str | Path) -> Drawing:
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.exists():
        raise ExtractionError(f"Drawing not found: {path}")
    if suffix == ".dwg":
        js, warnings = dwg_to_json(path, Path(cache_dir))
        d = load_slim_json(js, warnings)
        d.source = path.name
        return d
    if suffix == ".dxf":
        return load_dxf(path)
    if suffix == ".json":
        return load_slim_json(path)
    raise ExtractionError(f"Unsupported drawing format '{suffix}' (expected .dwg, .dxf or converter .json)")

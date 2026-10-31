"""Splice Connections Report reader (one .xlsx per splice point).

Sections in each report:
* header  : Splice name, Location, Address, Coordinates, Enclosure Type
* segments: Segment | Count | Start Splice | End Splice | Owner | Cable Design Length | Asbuilt
            ("Segment N of <cable> - <Underground|Aerial|Pigtail>"), plus splitter rows
            such as "PLC COUPLER 64 1 FE0-F1PLC64".
* fibers  : A-cable/B-cable connection table. Rows joining two segments of the
            same cable are pass-throughs, not fusion splices.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

SEG_RE = re.compile(r"^Segment\s+(\d+)\s+of\s+(.+?)\s+-\s+(\w+)\s*$")
COUPLER_RE = re.compile(r"^PLC COUPLER\s+(\d+)\s+(\d+)\s+(\S+)", re.I)
NAME_NET_RE = re.compile(r"^([A-Z]+)-(\d{2})\d{3}[A-Z]?$")


@dataclass
class Segment:
    name: str
    cable: str
    seg_no: int
    placement: str  # Underground | Aerial | Pigtail
    fibers: int
    start: str
    end: str
    design_length: float | None


@dataclass
class SpliceReport:
    path: str
    name: str
    network: str
    enclosure: str
    coords: tuple[float, float] | None
    segments: list[Segment] = field(default_factory=list)
    couplers: list[tuple[int, str]] = field(default_factory=list)  # (split ratio, part number)
    connections: int = 0
    fusion_splices: int = 0
    pass_through: int = 0
    format: str = "connections report"
    issues: list[str] = field(default_factory=list)  # cells that could not be read


def _number(v) -> float | None:
    """Cell number tolerant of text exports: 1234, '1,234', '48 ct', '1234 ft'; None if not a number."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.match(r"^\s*(-?[\d,]*\.?\d+)", str(v or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def network_from_splice_name(name: str) -> str | None:
    m = NAME_NET_RE.match(name.strip())
    return f"{m.group(1)}-R{m.group(2)}" if m else None


def _cable_of(seg_ref: str) -> str:
    return re.sub(r":\s*Seg\d+$", "", seg_ref.strip())


GUIDE_CABLE_RE = re.compile(r"^(.+?)\s*:\s*Seg\s*(\d+)\s*-\s*(\d+)\s*ct", re.I)
GUIDE_FIBER_RE = re.compile(r"\s+SEG-?\d+\s*$", re.I)


def _read_splice_guide(path: Path, rows: list[list]) -> SpliceReport:
    """Alternative layout 'Fiber Optic Splice Guide': labels in column B, values in E,
    In / Out cables in columns K / O, fiber rows pair column B (in) with column H (out)."""
    rep = SpliceReport(str(path), "", "", "", None)
    rep.format = "splice guide"
    seen = set()
    for r in rows[:14]:
        r = list(r) + [None] * 16
        label = str(r[1] or "").strip().rstrip(":").lower()
        if label == "splice name":
            rep.name = str(r[4] or "").strip()
        elif label == "enclosure make/model":
            rep.enclosure = str(r[4] or "").strip()
        for col in (10, 14):
            m = GUIDE_CABLE_RE.match(str(r[col] or "").strip())
            if m and m.group(0) not in seen:
                seen.add(m.group(0))
                cable = re.sub(r"\s+", " ", m.group(1)).strip()
                placement = "Pigtail" if re.search(r"FC00[1-8]$", cable) else "Underground"
                rep.segments.append(Segment(f"Segment {m.group(2)} of {cable} - {placement}", cable, int(m.group(2)),
                                            placement, int(m.group(3)), "", "", None))
    for r in rows[14:]:
        r = list(r) + [None] * 16
        a, b = r[1], r[7]
        if not a or not b:
            continue
        rep.connections += 1
        ca = GUIDE_FIBER_RE.sub("", str(a)).strip()
        cb = GUIDE_FIBER_RE.sub("", str(b)).strip()
        if re.sub(r"\s+", " ", ca) == re.sub(r"\s+", " ", cb):
            rep.pass_through += 1
        else:
            rep.fusion_splices += 1
    rep.name = rep.name or path.stem
    rep.network = network_from_splice_name(rep.name) or path.parent.name
    return rep


def read_splice_report(path: str | Path) -> SpliceReport:
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    if rows and any(str(v or "").strip().upper() == "FIBER OPTIC SPLICE GUIDE" for v in rows[0][:3]):
        return _read_splice_guide(path, rows)
    hdr: dict[str, list] = {}
    mode = None
    rep = SpliceReport(str(path), "", "", "", None)
    for r in rows:
        a = r[0] if r else None
        if isinstance(a, str) and a.strip().endswith(":") and mode is None:
            hdr[a.strip().rstrip(":").strip()] = r[1:]
            continue
        if a == "Segment" and len(r) > 1 and r[1] == "Count":
            mode = "seg"
            continue
        if a == "A Cable":
            mode = "fib_hdr"
            continue
        if mode == "fib_hdr" and a == "Segment":
            mode = "fib"
            continue
        if mode == "seg" and isinstance(a, str) and a.strip():
            m = SEG_RE.match(a.strip())
            if m:
                fibers, length = _number(r[1]), _number(r[5])
                if fibers is None and r[1] not in (None, ""):
                    rep.issues.append(f"{a.strip()}: fiber count '{r[1]}' not a number")
                if length is None and r[5] not in (None, ""):
                    rep.issues.append(f"{a.strip()}: design length '{r[5]}' not a number")
                rep.segments.append(
                    Segment(a.strip(), m.group(2).strip(), int(m.group(1)), m.group(3), int(fibers or 0),
                            str(r[2] or ""), str(r[3] or ""), length)
                )
            else:
                cm = COUPLER_RE.match(a.strip())
                if cm:
                    rep.couplers.append((int(cm.group(1)), cm.group(3)))
        elif mode == "fib" and a is not None:
            b_seg = r[10] if len(r) > 10 else None
            if r[4] is None or r[6] is None or not b_seg:
                continue
            rep.connections += 1
            if _cable_of(str(a)) == _cable_of(str(b_seg)):
                rep.pass_through += 1
            else:
                rep.fusion_splices += 1
    rep.name = str((hdr.get("Splice name") or [""])[0] or path.stem).strip()
    rep.enclosure = str((hdr.get("Enclosure Type") or [""])[0] or "").strip()
    c = hdr.get("Coordinates") or []
    if len(c) >= 2 and isinstance(c[0], (int, float)) and isinstance(c[1], (int, float)):
        rep.coords = (float(c[0]), float(c[1]))
    rep.network = network_from_splice_name(rep.name) or path.parent.name
    return rep


def read_splice_reports(paths: list[str | Path], errors: list[str] | None = None) -> list[SpliceReport]:
    """Read every report. A file that cannot be read is skipped and listed in `errors` (one bad
    report must not stop the BOM); without an `errors` list the exception propagates."""
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(x for x in p.rglob("*.xlsx") if not x.name.startswith("~$"))
        elif p.suffix.lower() == ".xlsx":
            files.append(p)
    out = []
    for f in files:
        try:
            out.append(read_splice_report(f))
        except Exception as exc:  # corrupt / unexpected layout
            if errors is None:
                raise
            errors.append(f"{f.name}: {exc.__class__.__name__}: {exc}")
    return out

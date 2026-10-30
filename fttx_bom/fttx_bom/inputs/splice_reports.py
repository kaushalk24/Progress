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


def network_from_splice_name(name: str) -> str | None:
    m = NAME_NET_RE.match(name.strip())
    return f"{m.group(1)}-R{m.group(2)}" if m else None


def _cable_of(seg_ref: str) -> str:
    return re.sub(r":\s*Seg\d+$", "", seg_ref.strip())


def read_splice_report(path: str | Path) -> SpliceReport:
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
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
                rep.segments.append(
                    Segment(a.strip(), m.group(2).strip(), int(m.group(1)), m.group(3), int(r[1] or 0),
                            str(r[2] or ""), str(r[3] or ""), float(r[5]) if r[5] not in (None, "") else None)
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


def read_splice_reports(paths: list[str | Path]) -> list[SpliceReport]:
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(x for x in p.rglob("*.xlsx") if not x.name.startswith("~$"))
        elif p.suffix.lower() == ".xlsx":
            files.append(p)
    return [read_splice_report(f) for f in files]

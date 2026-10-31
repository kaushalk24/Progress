"""Address-list reader (output of the separate address-list automation).

Layout (one sheet per network, sheet title = network name e.g. NMK-R02):
PON NAME | PON PORT | FIBER # | ADDRESS | COLOR TUBE | COLOR FIBER |
CABLE NAME | Fiber Tap Name | Fiber Splice
A served passing is a row with a PON NAME and PON PORT whose ADDRESS is not
the OLM power port.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

EXPECTED = ["PON NAME", "PON PORT", "FIBER #", "ADDRESS", "COLOR TUBE", "COLOR FIBER", "CABLE NAME", "Fiber Tap Name", "Fiber Splice"]


@dataclass
class ServedAddress:
    pon: int
    port: int
    address: str
    cable: str
    tap: str
    splice: str

    @property
    def tap_is_commercial(self) -> bool:
        return "-R-C-" in self.tap.upper()


@dataclass
class AddressList:
    network: str
    path: str
    served: list[ServedAddress] = field(default_factory=list)
    cables: list[str] = field(default_factory=list)
    power_ports: int = 0
    coupler_ratios: list[int] = field(default_factory=list)  # from 'PLC COUPLER <ratio> <n> COM' rows
    issues: list[str] = field(default_factory=list)

    @property
    def passings(self) -> int:
        return len(self.served)

    @property
    def pon_count(self) -> int:
        return len({a.pon for a in self.served})


def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


REQUIRED = ["PON NAME", "PON PORT", "ADDRESS"]


def _columns(header: list[str]) -> dict[str, int] | None:
    """Column index per EXPECTED name, matched case-insensitively and ignoring spaces; None when a
    required column is missing (the sheet is not an address list)."""
    def key(h):
        return re.sub(r"[^A-Z0-9#]", "", h.upper())

    pos = {}
    for i, h in enumerate(header):
        k = key(h)
        for name in EXPECTED:
            if k == key(name) and name not in pos:
                pos[name] = i
    return pos if all(r in pos for r in REQUIRED) else None


def read_address_list(path: str | Path, skipped: list[str] | None = None) -> list[AddressList]:
    """One AddressList per sheet with an address-list header. Other sheets (notes, pivots) are
    skipped and reported in `skipped`."""
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = [_norm(h) for h in rows[0]]
        col = _columns(hdr)
        if col is None:
            if skipped is not None:
                skipped.append(f"{path.name} sheet '{ws.title}': no PON NAME / PON PORT / ADDRESS header - not an address list, skipped")
            continue
        al = AddressList(network=ws.title.strip(), path=str(path))
        if [hdr[col[n]] if n in col else None for n in EXPECTED] != EXPECTED:
            al.issues.append(f"header differs from the standard export {EXPECTED}: {hdr[:12]} (columns matched by name)")

        def get(r, name):
            i = col.get(name)
            return r[i] if i is not None and i < len(r) else None

        cables = []
        for r in rows[1:]:
            r = list(r)
            cable = _norm(get(r, "CABLE NAME"))
            if cable and cable not in cables:
                cables.append(cable)
            addr = _norm(get(r, "ADDRESS"))
            cm = re.match(r"^PLC COUPLER\s+(\d+)\s+\d+\s+COM", addr, re.I)
            if cm:
                al.coupler_ratios.append(int(cm.group(1)))
            pon, port = get(r, "PON NAME"), get(r, "PON PORT")
            if pon is None or port is None:
                continue
            if addr.upper().startswith("POWER PORT"):
                al.power_ports += 1
                continue
            try:
                al.served.append(ServedAddress(int(pon), int(port), addr, cable, _norm(get(r, "Fiber Tap Name")),
                                               _norm(get(r, "Fiber Splice"))))
            except (TypeError, ValueError):
                al.issues.append(f"non-numeric PON/port in row {r[:4]}")
        al.cables = cables
        out.append(al)
    wb.close()
    return out


def read_address_lists(paths: list[str | Path], skipped: list[str] | None = None) -> dict[str, AddressList]:
    result: dict[str, AddressList] = {}
    for p in paths:
        for al in read_address_list(p, skipped):
            if al.network in result:
                raise ValueError(f"network {al.network} appears in more than one address list")
            result[al.network] = al
    return result

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


def read_address_list(path: str | Path) -> list[AddressList]:
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = [_norm(h) for h in rows[0][: len(EXPECTED)]]
        al = AddressList(network=ws.title.strip(), path=str(path))
        if hdr != EXPECTED:
            al.issues.append(f"unexpected header {hdr}")
            out.append(al)
            continue
        cables = []
        for r in rows[1:]:
            r = list(r) + [None] * (len(EXPECTED) - len(r))
            cable = _norm(r[6])
            if cable and cable not in cables:
                cables.append(cable)
            cm = re.match(r"^PLC COUPLER\s+(\d+)\s+\d+\s+COM", _norm(r[3]), re.I)
            if cm:
                al.coupler_ratios.append(int(cm.group(1)))
            if r[0] is None or r[1] is None:
                continue
            addr = _norm(r[3])
            if addr.upper().startswith("POWER PORT"):
                al.power_ports += 1
                continue
            try:
                al.served.append(ServedAddress(int(r[0]), int(r[1]), addr, cable, _norm(r[7]), _norm(r[8])))
            except (TypeError, ValueError):
                al.issues.append(f"non-numeric PON/port in row {r[:4]}")
        al.cables = cables
        out.append(al)
    wb.close()
    return out


def read_address_lists(paths: list[str | Path]) -> dict[str, AddressList]:
    result: dict[str, AddressList] = {}
    for p in paths:
        for al in read_address_list(p):
            if al.network in result:
                raise ValueError(f"network {al.network} appears in more than one address list")
            result[al.network] = al
    return result

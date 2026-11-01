#!/usr/bin/env python3
"""Unit tests for the parsing / numbering rules + the synthetic-region end-to-end self-test.

    python tests/run_tests.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fcs import engine as E  # noqa: E402
from fcs.selftest import run_selftest  # noqa: E402

RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))


def test_numbering_helpers() -> None:
    check("to_index plain", E.to_index(3) == 3 and E.to_index(3.0) == 3 and E.to_index("3") == 3)
    check("to_index text", E.to_index("PON 3") == 3 and E.to_index("P-03") == 3 and E.to_index("Port 12") == 12)
    check("to_index empty", E.to_index(None) is None and E.to_index("") is None and E.to_index("Spare") is None)
    check("runs", E.number_runs([5, 3, 4, 9, 10, 12]) == [(3, 5), (9, 10), (12, 12)])
    check("fmt span", E.fmt_numbers([3, 4, 5, 9, 90], "span") == "3-90")
    check("fmt exact", E.fmt_numbers([3, 4, 5, 9, 90], "exact") == "3-5,9,90")
    check("fmt single", E.fmt_numbers([51], "span") == "51")
    check("zero pad", E.fmt_run((3, 9), 2) == "03-09")


def test_callout_text_rules() -> None:
    for t in ("12", "218-219", "BFO 144\\P3-90", "BFO 72\n70-115", "03", "BFO 24\\P13"):
        check(f"is callout {t!r}", E.is_fiber_callout_text(t))
    for t in ("NMK-02001G", "FC072", "86'", "MAPLE AVE", "BFO", "72F"):
        check(f"is not callout {t!r}", not E.is_fiber_callout_text(t))
    check("canonical", E.canonical_callout_text("BFO 024\\P08-09") == "BFO 24|8-9")


def test_address_rules() -> None:
    v = E.AddressBook.address_variants("C-9030 247th st e")
    check("commercial prefix variant", "9030 247TH ST E" in v, str(v))
    v = E.AddressBook.address_variants("22880 #2 PENN AVE")
    check("unit token variant", "22880 PENN AVE" in v, str(v))
    check("strip kind", E.strip_kind("Splice Case: NMK-02001G") == "NMK-02001G")
    check("strip kind keeps usage", E.strip_kind("NMK-02001G") == "NMK-02001G")
    check("olm from file name", E.derive_olm("386106_Credit River MN_NMK-R02_FTTH_Address List",
                                             "386106_Credit River MN_NMK-R02_FTTH_Address List.csv") == "NMK-R02")
    check("olm from sheet", E.derive_olm("NMK-R03", "whatever.xlsx") == "NMK-R03")


def test_header_mapping() -> None:
    cm = E.auto_map_columns(["PON NAME", "PON PORT", "FIBER #", "ADDRESS", "COLOR TUBE", "COLOR FIBER", "CABLE NAME",
                             "Fiber Tap Name", "Fiber Splice"])
    check("credit river headers", (cm.pon, cm.port, cm.address, cm.tap, cm.splice) ==
          ("PON NAME", "PON PORT", "ADDRESS", "Fiber Tap Name", "Fiber Splice"), str(cm))
    cm = E.auto_map_columns(["OLT PON", "Splitter Port", "Strand", "Premise Address", "Terminal ID", "Splice Enclosure"])
    check("vendor headers", (cm.pon, cm.port, cm.address, cm.tap, cm.splice) ==
          ("OLT PON", "Splitter Port", "Premise Address", "Terminal ID", "Splice Enclosure"), str(cm))


def test_splitter_detection() -> None:
    def size(t: str):
        m = E.SPLITTER_RE.search(t)
        return [g for g in m.groups() if g][0] if m else None
    check("splitter PLC COUPLER", size("PLC COUPLER 64 1 FE0-F1PLC64") == "64")
    check("splitter not coupler id", size("PLCCOUPLER321") is None)
    check("splitter 1x32", size("Splitter 1x32") == "32")


def test_report_parsers() -> None:
    rows = [["Splice Connections Report"], ["Splice name:", "ABC-00002"], ["Coordinates:", 10.5, 20.25],
            ["Segment", "Count", "Start Splice", "End Splice", "Owner"],
            ["Segment 2 of ABC-00001G TO ABC-00009G FC048 - Underground", 48, "Splice Case: ABC-00001G", "Splice Case: ABC-00002"],
            ["Segment 3 of ABC-00001G TO ABC-00009G FC048 - Underground", 48, "Splice Case: ABC-00002", "Splice Case: ABC-00003"],
            [], ["A Cable", None, None, None, None, None, "B Cable"],
            ["Segment", "Group 3", "Group 2", "Fiber", "#", "Dir", "#", "Fiber", "Group 2", "Group 3", "Segment", "Usage", "State"],
            ["ABC-00001G TO ABC-00009G FC048: Seg2", None, "blue", "blue", "01.01(1)", "<-", "01.01(1)", "blue", "blue", None,
             "ABC-00001G TO ABC-00009G FC048: Seg3", "ABC-T-1 MAIN ST:1 1 MAIN ST", "Return"]]
    r = E.parse_connections_report(rows, "x.xlsx")
    check("connections parse name/xy", r is not None and r.name == "ABC-00002" and r.xy == (10.5, 20.25))
    check("connections segments", r is not None and [(s.seg, s.direction) for s in r.segments] == [(2, "in"), (3, "out")])
    check("connections usage", r is not None and r.conns[0].tap == "ABC-T-1 MAIN ST" and r.conns[0].port_idx == 1
          and r.conns[0].b_seg == ("ABC-00001G TO ABC-00009G FC048", 3))


def main() -> int:
    for fn in (test_numbering_helpers, test_callout_text_rules, test_address_rules, test_header_mapping,
               test_splitter_detection, test_report_parsers):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            RESULTS.append((fn.__name__, False, f"{exc}\n{traceback.format_exc()}"))
    ok_st, text = run_selftest(verbose=False)
    RESULTS.append(("synthetic region end-to-end self-test", ok_st, text if not ok_st else ""))
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if not ok and detail else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

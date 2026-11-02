#!/usr/bin/env python3
"""Unit tests for the parsing / numbering rules + the synthetic-region end-to-end self-test.

    python tests/run_tests.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
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


def test_decorated_segment_ends() -> None:
    rows = [["Splice Connections Report"], ["Splice name:", "DMI-15122G"],
            ["Segment", "Count", "Start Splice", "End Splice"],
            ["Segment 3 of DMI-15001G TO DMI-15200 FC072 - Underground", 72, "Splice Case: DMI-15100",
             "Splice Case: DMI-15122G (HH 12)"],
            ["Segment 1 of DMI-15122G TO DMI-15140 FC048 - Underground", 48, "DMI-15122G HH", "DMI-15140"]]
    r = E.parse_connections_report(rows, "x.xlsx")
    check("segment direction with decorated closure names",
          r is not None and [s.direction for s in r.segments] == ["in", "out"], str(r and r.segments))


def test_junction_rule() -> None:
    pl = E.CalloutPlanner.__new__(E.CalloutPlanner)
    S = E.ReportSegment

    def rep(name, segs):
        return [E.SpliceReport(name=name, file="x", fmt="t", segments=segs)]
    closures = {"A-1", "A-2", "A-3", "A-4", "A-9"}
    trunk_in = S("A-1 TO A-9 FC144", 4, 144, "Underground", "A-1", "A-2", "in")
    trunk_out = S("A-1 TO A-9 FC144", 5, 144, "Underground", "A-2", "A-3", "out")
    pig = S("A-2 TO T-10 MAIN ST FC004", 1, 4, "Pigtail", "A-2", "T-10 MAIN ST", "out")
    tap24 = S("A-2 TO T-10 MAIN ST FC024", 1, 24, "Underground", "A-2", "T-10 MAIN ST", "out")
    tail12 = S("A-2 TO MST 7 FC012", 1, 12, "Underground", "A-2", "MST 7", "out")
    branch = S("A-2 TO A-4 FC024", 1, 24, "Underground", "A-2", "A-4", "out")
    taper = S("A-2 TO A-3 FC072", 1, 72, "Underground", "A-2", "A-3", "out")
    j = lambda segs: pl.junction_info("A-2", rep("A-2", segs), closures)[0]  # noqa: E731
    check("junction: cable branches (3 segments)", j([trunk_in, trunk_out, branch, pig]))
    check("junction: 24F cable to a terminal counts", j([trunk_in, trunk_out, tap24]))
    check("pass-through: pigtail does not count", not j([trunk_in, trunk_out, pig]))
    check("pass-through: 12F terminal tail does not count", not j([trunk_in, trunk_out, tail12]))
    check("pass-through: taper 144->72 is not a junction", not j([trunk_in, taper, pig]))
    check("junction: feed not listed, 2 cables out", j([trunk_out, branch]))
    check("pass-through: duplicate rows counted once", not j([trunk_in, trunk_out, trunk_out, pig]))


def test_text_tables() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        def write(name: str, data: bytes) -> Path:
            f = Path(tmp) / name
            f.write_bytes(data)
            return f
        f = write("semi.csv", 'Splice name:;NMK-1\r\nCoordinates:;1552147,5;16207889,25\r\n"Addr";"12 RUE, \u00c9\nLINE2"\r\n'
                  .encode("cp1252"))
        rows = E.read_text_table(f)
        check("csv semicolon / cp1252 / comma decimals", rows[0] == ["Splice name:", "NMK-1"]
              and rows[1] == ["Coordinates:", 1552147.5, 16207889.25] and rows[2][1] == "12 RUE, \u00c9\nLINE2", str(rows))
        f = write("u16.txt", "PON\tPORT\tADDRESS\r\n1\t12\t100 MAIN ST\r\n".encode("utf-16"))
        rows = E.read_text_table(f)
        check("utf-16 tab-delimited text", rows == [["PON", "PORT", "ADDRESS"], [1, 12, "100 MAIN ST"]], str(rows))
        f = write("sep.csv", b"sep=;\ra;b\r1;2\r")
        rows = E.read_text_table(f)
        check("excel sep= line with CR line ends", rows == [["a", "b"], [1, 2]], str(rows))
        f = write("bom.csv", b'\xef\xbb\xbfPON,PORT,ID,Z\n01,="00123",0012,\n')
        rows = E.read_text_table(f)
        check("csv BOM / leading zeros / trailing blanks", rows == [["PON", "PORT", "ID", "Z"], ["01", "00123", "0012"]], str(rows))
        wb = E.openpyxl.Workbook()
        for i in range(5):
            wb.active.append([f"r{i}", i])
        xf = Path(tmp) / "dim.xlsx"
        wb.save(xf)
        import zipfile as zf
        tmpf = Path(tmp) / "dim2.xlsx"
        with zf.ZipFile(xf) as zin, zf.ZipFile(tmpf, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith("sheet1.xml"):
                    data = data.replace(b'<dimension ref="A1:B5"/>', b'<dimension ref="A1"/>')
                zout.writestr(item, data)
        tables = E.read_tables(tmpf)
        check("xlsx with a wrong stored used range", len(tables[0][1]) == 5 and tables[0][1][4] == ["r4", 4], str(tables))
        try:
            import xlwt  # type: ignore
        except ImportError:
            return
        book = xlwt.Workbook()
        sh = book.add_sheet("NMK-R02")
        for r, row in enumerate([["PON", "PORT", None, "ADDRESS"], [1, 12.0, None, "100 MAIN ST"]]):
            for c, v in enumerate(row):
                if v is not None:
                    sh.write(r, c, v)
        book.save(str(Path(tmp) / "old.xls"))
        tables = E.read_tables(Path(tmp) / "old.xls")
        check("legacy .xls", tables == [("NMK-R02", [["PON", "PORT", None, "ADDRESS"], [1, 12, None, "100 MAIN ST"]])],
              str(tables))


def test_units() -> None:
    def f(code):
        src = E.NetworkSource("dxf", "x", "AC1032", None, [], [], [], [], insunits=code)
        return E.units_factor(src, "auto", E.Reporter(lambda m, l: None))
    check("units: inches template default = feet", f(1) == 1.0)
    check("units: feet / US survey feet", f(2) == 1.0 and f(21) == 1.0)
    check("units: meters / millimeters rescale", abs(f(6) - 0.3048) < 1e-9 and abs(f(4) - 304.8) < 1e-9)
    check("units: unknown = feet", f(None) == 1.0 and f(0) == 1.0)


def test_input_signature() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "data"
        folder.mkdir()
        f = folder / "list.csv"
        f.write_text("PON,PORT\n1,1\n", encoding="utf-8")
        cfg = E.RunConfig(drawing_path=str(Path(tmp) / "d.dxf"), splice_paths=[str(folder)], address_paths=[str(folder)])
        before = E.input_signature(cfg)
        check("signature stable", before == E.input_signature(cfg))
        dir_mtime = folder.stat().st_mtime_ns
        f.write_text("PON,PORT\n1,2\n", encoding="utf-8")       # edited in place
        os.utime(f, ns=(time.time_ns(), f.stat().st_mtime_ns + 1_000_000))
        os.utime(folder, ns=(dir_mtime, dir_mtime))
        check("signature sees file edited inside a folder", before != E.input_signature(cfg))


def test_output_folder_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        blocker = Path(tmp) / "not_a_folder"
        blocker.write_text("x", encoding="utf-8")
        cfg = E.RunConfig(drawing_path=str(Path(tmp) / "d.dxf"), output_dir=str(blocker / "out"))
        eng = E.CalloutEngine(cfg, E.Reporter(lambda m, l: None))
        res = E.RunResult([], [], [], E.IssueLog(), {}, [], [], {}, {})
        try:
            eng.export(res)
            check("unwritable output folder reported", False, "no error raised")
        except RuntimeError as exc:
            check("unwritable output folder reported", "Cannot write to the output folder" in str(exc), str(exc))


def main() -> int:
    for fn in (test_numbering_helpers, test_callout_text_rules, test_address_rules, test_header_mapping,
               test_splitter_detection, test_report_parsers, test_decorated_segment_ends, test_junction_rule, test_text_tables, test_units, test_input_signature, test_output_folder_error):
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

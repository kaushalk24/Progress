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
    sv = E.splitter_values
    check("splitter 'PLC COUPLER 64 1 FE0-F1PLC64'", sv("PLC COUPLER 64 1 FE0-F1PLC64") == [64, 64])
    check("coupler id PLCCOUPLER641 = size 64, output coupler 1", sv("PLCCOUPLER641") == [64])
    check("coupler id PLCCOUPLER6410 = size 64, output coupler 10", sv("PLCCOUPLER6410") == [64])
    check("PLCCOUPLEF64 (spelling with EF)", sv("PLCCOUPLEF64") == [64])
    check("coupler id PLCCOUPLER321 = size 32, output coupler 1", sv("PLCCOUPLER321") == [32])
    check("coupler id PLCCOUPLER32 = size 32", sv("PLCCOUPLER32") == [32])
    check("ratio wordings 1x32 / 1:16 / PLC 1:8 / 1x8 PLC", sv("Splitter 1x32") == [32] and sv("SPLITTER 1:16") == [16]
          and sv("PLC 1:8") == [8] and sv("1x8 PLC") == [8])
    check("no splitter in other text", sv("Generic Rack 19x40x6: New Market MN NMK(01:1:2)") == []
          and sv("NMK-02001G") == [] and sv("PLCCOUPLER3") == [] and sv("COUPLER 1") == [])


def test_olm_splitters() -> None:
    def hub(name, sizes, feed_olm):
        segs = [E.ReportSegment(cable=f"{feed_olm} TO {name} FC024", seg=1, count=24, kind="Underground",
                                start=name, end=feed_olm, direction="out")]
        return E.SpliceReport(name=name, file="x", fmt="t", segments=segs, splitters=list(sizes))
    reps = [hub("NMK-02001G", [64, 64, 64], "NMK-R02"), hub("NMK-03001G", [32], "NMK-R03"),
            E.SpliceReport(name="NMK-02006", file="y", fmt="t")]
    got = E.olm_splitters(reps, {"NMK-R02", "NMK-R03", "NMK-R04"})
    check("OLM splitter from the 0001G splice case of its feed", got == {"NMK-R02": 64, "NMK-R03": 32}, str(got))


def test_per_olm_numbering() -> None:
    import openpyxl
    hubs = [E.SpliceReport(name="NMK-02001G", file="a", fmt="t", splitters=[64],
                           segments=[E.ReportSegment(cable="NMK-R02 TO NMK-02001G FC024", seg=1, count=24,
                                                     kind="Underground", start="NMK-02001G", end="NMK-R02",
                                                     direction="out")]),
            E.SpliceReport(name="NMK-03001G", file="b", fmt="t", splitters=[32],
                           segments=[E.ReportSegment(cable="NMK-R03 TO NMK-03001G FC024", seg=1, count=24,
                                                     kind="Underground", start="NMK-03001G", end="NMK-R03",
                                                     direction="out")])]
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for sheet in ("NMK-R02", "NMK-R03", "NMK-R04"):
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet
            ws.append(["PON NAME", "PON PORT", "ADDRESS", "Fiber Tap Name", "Fiber Splice"])
            ws.append([2, 5, "100 MAIN ST", "NMK-R-T1", "NMK-02006"])
            path = Path(tmp) / f"{sheet}.xlsx"
            wb.save(path)
            paths.append(path)
        issues = E.IssueLog()
        book = E.AddressBook()
        book.load(paths, E.ColumnMap(), 0, hubs, {}, issues, E.Reporter(lambda m, l: None))
        nums = {r.olm: r.number for r in book.records}
    check("fiber number of an OLM with a 64F splitter", nums.get("NMK-R02") == 69, str(nums))
    check("fiber number of an OLM with a 32F splitter", nums.get("NMK-R03") == 37, str(nums))
    est = [i for i in issues.items if i.severity == "WARNING" and "ESTIMATED" in i.message]
    check("OLM without a splitter size is estimated and warned", nums.get("NMK-R04") == 13 and len(est) == 1, str(nums))


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
    from collections import defaultdict
    from types import SimpleNamespace as NS
    pl = E.CalloutPlanner.__new__(E.CalloutPlanner)
    pl._touching = defaultdict(set)
    S = E.ReportSegment

    def rep(name, segs, conns=(), splitters=()):
        return [E.SpliceReport(name=name, file="x", fmt="t", segments=list(segs), conns=list(conns),
                               splitters=list(splitters))]
    closures = {"A-1", "A-2", "A-3", "A-4", "A-9"}
    trunk_in = S("A-1 TO A-9 FC144", 4, 144, "Underground", "A-1", "A-2", "in")
    trunk_out = S("A-1 TO A-9 FC144", 5, 144, "Underground", "A-2", "A-3", "out")
    pig = S("A-2 TO T-10 MAIN ST FC004", 1, 4, "Pigtail", "A-2", "T-10 MAIN ST", "out")
    tap24 = S("A-2 TO T-10 MAIN ST FC024", 1, 24, "Underground", "A-2", "T-10 MAIN ST", "out")
    tail12 = S("A-2 TO MST 7 FC012", 1, 12, "Underground", "A-2", "MST 7", "out")
    branch = S("A-2 TO A-4 FC024", 1, 24, "Underground", "A-2", "A-4", "out")
    end96 = S("A-1 TO A-2 FC096", 22, 96, "Underground", "A-1", "A-2", "in")       # 96F cable ends here
    new72 = S("A-2 TO A-3 FC072", 1, 72, "Underground", "A-2", "A-3", "out")       # a new 72F cable starts here
    new96 = S("A-2 TO A-3 FC096", 1, 96, "Underground", "A-2", "A-3", "out")       # new cable, same fiber count

    pl.labels = {}

    def role(segs):
        reps = rep("A-2", segs)
        dirs = {(x.cable, x.seg): x.direction for x in segs}
        junction, ins, in_ids, _d = pl.closure_role("A-2", reps, closures, dirs)
        outs = [x for x in segs if x.direction == "out" and not pl.is_tail("A-2", x, closures)]
        return junction, [pl.is_new_cable(x, ins, in_ids) for x in outs] if in_ids else []
    check("junction: cable branches (3 segments)", role([trunk_in, trunk_out, branch, pig])[0])
    check("junction: 24F cable to a terminal counts", role([trunk_in, trunk_out, tap24])[0])
    check("pass-through: pigtail does not count", role([trunk_in, trunk_out, pig]) == (False, [False]))
    check("pass-through: 12F terminal tail does not count", role([trunk_in, trunk_out, tail12]) == (False, [False]))
    check("cable change: 96F ends, 72F starts -> BFO on the 72F", role([end96, new72, pig]) == (False, [True]))
    check("cable change: different cable, same fiber count (96F -> 96F)", role([end96, new96, pig]) == (False, [True]))
    same96_in = S("A-1 TO A-9 FC096", 7, 96, "Underground", "A-1", "A-2", "in")
    reused = S("A-1 TO A-9 FC096", 1, 96, "Underground", "A-2", "A-3", "out")
    backwards = S("A-1 TO A-9 FC096", 6, 96, "Underground", "A-2", "A-3", "out")
    check("cable change: name reused by a new cable (seg 7 in, seg 1 out)", role([same96_in, reused, pig]) == (False, [True]))
    check("same cable drawn backwards (seg 7 in, seg 6 out)", role([same96_in, backwards, pig]) == (False, [False]))
    drop4 = S("A-2 TO A-4 FC004", 1, 4, "Underground", "A-2", "A-4", "out")
    check("4F to another closure is a drop, not a cable", role([trunk_in, trunk_out, drop4]) == (False, [False]))
    mdu24 = S("A-2 TO MDU 10 MAIN ST FC024", 1, 24, "Pigtail", "A-2", "MDU 10 MAIN ST", "out")
    check("24F MDU cable called 'Pigtail' is still a cable (junction)", role([trunk_in, trunk_out, mdu24])[0])
    check("same cable, FC0144 vs FC144 spelling", pl.cable_id("A TO B FC0144") == pl.cable_id("A TO B FC144"))
    check("junction: feed not listed, 2 cables out", role([trunk_out, branch])[0])
    dup = role([trunk_in, trunk_out, trunk_out, pig])
    check("pass-through: duplicate rows counted once", dup[0] is False and not any(dup[1]), str(dup))
    pl._touching["A-2"] = {("A-1 TO A-2 FC096", 22)}
    check("cable change: feed taken from the neighbour's report", role([new72, pig]) == (False, [True]))
    pl._touching.clear()
    check("far end of a backwards-digitized segment", E.CalloutPlanner.far_node("A-2", "A-3", "A-2") == "A-3"
          and E.CalloutPlanner.far_node("A-2", "A-2", "A-3") == "A-3")

    # fiber flow: the report lists the 72F as 'in' (digitized backwards); the fibers arrive on the 96F
    rec = {"T1": NS(olm="R1", number=1), "T2": NS(olm="R1", number=2), "T3": NS(olm="R1", number=3)}
    pl.book = NS(resolve_candidates=lambda tap, addr, olm, idx: [rec[tap]] if tap in rec else [])
    f72 = S("A-9 TO A-2 FC072", 11, 72, "Underground", "A-9", "A-2", "in")
    f96 = S("A-1 TO A-2 FC096", 1, 96, "Underground", "A-2", "A-1", "out")
    f48 = S("A-2 TO A-4 FC048", 1, 48, "Underground", "A-2", "A-4", "out")
    k72, k96, k48 = (f72.cable, 11), (f96.cable, 1), (f48.cable, 1)

    def conn(a, b, tap):
        return E.ReportConn(a_seg=a, b_seg=b, usage=f"{tap}:1 X", state="Return", tap=tap, address="X", port_idx=1)
    rows = [conn(k96, k48, "T1"), conn(k96, k48, "T2"), conn(k72, k96, "T3")]
    pl.m = NS(closures={c: None for c in closures})
    pl.reports = []
    dirs, src = pl.flow_directions("A-2", rep("A-2", [f72, f96, f48], rows))
    check("fiber flow corrects backwards segments", src == "fiber flow" and dirs == {k72: "out", k96: "in", k48: "out"},
          str(dirs))
    dirs, src = pl.flow_directions("A-2", rep("A-2", [f72, f96], [conn(k72, k96, "T1")]))
    check("fiber flow: 2-segment tie keeps the report", src == "splice report" and dirs[k72] == "in", str(dirs))
    dirs, src = pl.flow_directions("A-2", rep("A-2", [f72, f96, f48], rows, splitters=[32]))
    check("fiber flow: splitter hub keeps the report", src == "splice report")
    hub_rows = [E.ReportConn(a_seg=None, b_seg=k72, usage="T1:1 X", state="Return", tap="T1", address="X", port_idx=1)]
    dirs, src = pl.flow_directions("A-2", rep("A-2", [f72, f96], hub_rows, splitters=[32]))
    check("fiber flow: hub cable fed by a splitter port is outgoing", src == "splitter hub" and dirs[k72] == "out", str(dirs))
    pl._upstream = {"A-2": {("R1", 1): k96, ("R2", 5): k72}}
    dirs, src = pl.flow_directions("A-2", rep("A-2", [f72, f96, f48], rows))
    check("fiber flow: merge closure with two feeds", src == "fiber flow" and dirs == {k72: "in", k96: "in", k48: "out"},
          str(dirs))
    pl._upstream = {}
    # 96F ends here and a new 96F starts, both listed 'out' (incoming drawn backwards), 1:1 splices only
    in_bw = S("A-1 TO A-2 FC096", 5, 96, "Underground", "A-2", "A-1", "out")
    out_new = S("A-2 TO A-3 FC096", 1, 96, "Underground", "A-2", "A-3", "out")
    tie = [conn((in_bw.cable, 5), (out_new.cable, 1), "T1")]
    dirs, src = pl.flow_directions("A-2", rep("A-2", [in_bw, out_new], tie))
    check("cable names decide when fiber flow cannot", src == "cable names"
          and dirs == {(in_bw.cable, 5): "in", (out_new.cable, 1): "out"}, f"{src} {dirs}")


def test_drawing_cable_labels() -> None:
    from ezdxf.math import Vec2
    lab = E.GeoInsert("1A", "Fiber Cable - Underground", "fiberinfo", Vec2(0, 0),
                      {"TTL": "96", "SEGNUM": "DMI-15001G TO DMI-15050 FC096", "TOTAL": "5732"}, [], (0, 0, 0, 0))
    txt = E.GeoText("2B", "ANNO", "MTEXT", "DMI-15050 TO DMI-15080 FC096\\P96F UG", Vec2(5, 5), Vec2(5, 5), (0, 0, 0, 0), 4.0)
    src = E.NetworkSource("dxf", "x", "AC1032", None, [], [lab], [], [txt])
    labels = E.drawing_cable_labels(src)
    check("drawing cable labels (block attribute + MText)",
          set(labels) == {"DMI-15001G TO DMI-15050 FC96", "DMI-15050 TO DMI-15080 FC96"}
          and labels["DMI-15001G TO DMI-15050 FC96"][0].count == 96, str(labels))
    check("cable name ends", E.cable_ends("DMI-15001G TO DMI-15050 FC096") == ("DMI-15001G", "DMI-15050"))


def test_name_mismatch_and_differences() -> None:
    book = E.AddressBook()
    for n, addr in ((200, "23636 LOGAN WAY"), (201, "23600 LOGAN WAY")):
        rec = E.AddressRecord(olm="R04", pon=4, port=n - 192, number=n, address=addr, tap="NMK-R-23636 LOGAN WAY",
                              splice="NMK-04109G", fiber=None, cable="", source="x", row=n)
        book.records.append(rec)
        book.by_tap[rec.tap].append(rec)
        book.by_tap_addr[(rec.tap, rec.address)].append(rec)
        book.by_addr[rec.address].append(rec)
        book.tap_names.add(rec.tap)
        book.loose_taps[E.loose_street(rec.tap)].add(rec.tap)
    got = book.resolve_candidates("NMK-R-23636 LOGAN AVE", "23636 LOGAN AVE", None, 1)
    check("terminal name with another street suffix (AVE vs WAY)", [r.number for r in got] == [200], str(got))
    check("suffix match needs the same house + street", not book.resolve_candidates("NMK-R-23636 OAK AVE", "23636 OAK AVE", None, 1))
    check("callout difference: range", E.describe_difference("BFO 24\\P132-133", "BFO 24\\P131-133") == "only in the drawing: 131")
    check("callout difference: fiber count", E.describe_difference("BFO 48\\P21-22", "BFO 24\\P21-22")
          == "fiber count: drawing 24, computed 48")
    check("callout difference: fiber number", E.describe_difference("109-110", "109") == "computed only: 110")


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
               test_splitter_detection, test_olm_splitters, test_per_olm_numbering, test_report_parsers, test_decorated_segment_ends, test_junction_rule, test_drawing_cable_labels, test_name_mismatch_and_differences, test_text_tables, test_units, test_input_signature, test_output_folder_error):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            RESULTS.append((fn.__name__, False, f"{exc}\n{traceback.format_exc()}"))
    ok_st, text = run_selftest(verbose=False)
    RESULTS.append(("synthetic region end-to-end self-test", ok_st, text if not ok_st else ""))
    ok_all, text = run_selftest(verbose=False, all_reports=True)
    RESULTS.append(("synthetic region with a splice report at every splice", ok_all, text if not ok_all else ""))
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if not ok and detail else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

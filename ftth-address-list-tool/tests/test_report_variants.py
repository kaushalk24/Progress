"""Report and network variants met in aerial / mixed regions (synthetic data, fictitious identifiers):

* a Node Facility without a report where the fibre is spliced onto another cable under another number;
* one span split into several sections (aerial pole-to-pole, riser, underground) - each closure report
  lists the section touching it;
* a closure exported as a 'Cable Report' (no segment numbers);
* two cables with the same name at one closure (two MDU buildings without a house number).
"""

from pathlib import Path

from ftth_addrlist.config import load_config
from ftth_addrlist.model import CableFiber
from ftth_addrlist.network import Network
from ftth_addrlist.splice_reports import FMT_CABLE, load_reports, read_report

from fixtures import cable_side, write_report

ORIGIN = "TST-00001G"
U1 = "TST-R-100 MAIN ST:1 100 MAIN ST"
U2 = "TST-R-200 MAIN ST:1 200 MAIN ST"
TERM = "MAX10 Enclosure(M Bulk): TST-R-{} MAIN ST"


def _net(folder: Path) -> Network:
    cfg = load_config()
    reps, issues = load_reports(sorted(folder.glob("*")), cfg)
    net = Network(reps, cfg)
    net.load_issues = issues
    return net


def _conn(a, b, usage, n, start=f"Splice Case: {ORIGIN}"):
    return {"a": a, "b": b, "usage": usage, "start": start, "end": TERM.format(n)}


# ------------------------------------------------------------------ node facility
def _node_region(folder: Path, *, twin: bool = False, foreign: bool = False):
    up = f"{ORIGIN} TO TST-W01 FC048"
    aer = "TST-W01 TO TST-00060 FC024"
    pig = "TST-00060 TO TST-R-100 MAIN ST FC004"
    write_report(folder / "A.xlsx", ORIGIN, [
        (f"{up}: Seg1", 48, f"Splice Case: {ORIGIN}", "Node Facility: TST-W01-A-00", "Underground")], [])
    conns = [_conn(cable_side(f"{aer}: Seg2", 1), cable_side(f"{pig}: Seg1", 1), U1, 100,
                   start="Splice Case: TST-00009G" if foreign else f"Splice Case: {ORIGIN}")]
    if twin:   # a second fibre of the same circuit: ambiguous, never guessed
        conns.append(_conn(cable_side(f"{aer}: Seg2", 2), cable_side(f"{pig}: Seg1", 2), U1, 100))
    write_report(folder / "B.xlsx", "TST-00060", [
        (f"{aer}: Seg2", 24, "Node Facility: TST-W01-A-00", "Splice Case: TST-00060", "Aerial"),
        (f"{pig}: Seg1", 4, "Splice Case: TST-00060", TERM.format(100), "Pigtail")], conns)
    return up


def test_node_facility_without_report_is_bridged_by_circuit(tmp_path):
    up = _node_region(tmp_path)
    net = _net(tmp_path)
    tr = net.trace(ORIGIN, CableFiber(up, 1, 5), U1)
    assert tr.stop == "terminal" and tr.last_closure == "TST-00060"
    assert tr.node_passes and "TST-W01-A-00" in tr.node_passes[0] and "TST-W01-A-00" in tr.route


def test_node_facility_bridge_needs_one_fibre_of_the_same_circuit(tmp_path):
    up = _node_region(tmp_path / "twin", twin=True)
    assert _net(tmp_path / "twin").trace(ORIGIN, CableFiber(up, 1, 5), U1).stop == "missing_report"
    up = _node_region(tmp_path / "foreign", foreign=True)   # same text, circuit from another hub
    assert _net(tmp_path / "foreign").trace(ORIGIN, CableFiber(up, 1, 5), U1).stop == "missing_report"


# ------------------------------------------------------------------ split span
def _span_region(folder: Path, *, between: bool = False):
    cab = f"{ORIGIN} TO TST-00030 FC024"
    pig = "TST-00030 TO TST-R-100 MAIN ST FC004"
    write_report(folder / "A.xlsx", ORIGIN, [
        (f"{cab}: Seg1", 24, f"Splice Case: {ORIGIN}", "Splice Case: TST-00030", "Aerial")], [])
    write_report(folder / "B.xlsx", "TST-00030", [
        (f"{cab}: Seg3", 24, f"Splice Case: {ORIGIN}", "Splice Case: TST-00030", "Underground"),
        (f"{pig}: Seg1", 4, "Splice Case: TST-00030", TERM.format(100), "Pigtail")],
        [_conn(cable_side(f"{cab}: Seg3", 1), cable_side(f"{pig}: Seg1", 1), U1, 100)])
    if between:   # Seg2 is listed elsewhere with other ends: a real numbering mismatch
        write_report(folder / "C.xlsx", "TST-00099", [
            (f"{cab}: Seg2", 24, "Splice Case: TST-00098", "Splice Case: TST-00099", "Underground")], [])
    return cab


def test_span_split_into_sections_is_not_a_numbering_mismatch(tmp_path):
    cab = _span_region(tmp_path)
    tr = _net(tmp_path).trace(ORIGIN, CableFiber(cab, 1, 1), U1)
    assert tr.stop == "terminal" and tr.last_closure == "TST-00030"
    assert tr.span_sections and not tr.seg_aliases


def test_segment_numbering_mismatch_still_flagged(tmp_path):
    cab = _span_region(tmp_path, between=True)
    tr = _net(tmp_path).trace(ORIGIN, CableFiber(cab, 1, 1), U1)
    assert tr.stop == "terminal" and tr.seg_aliases and not tr.span_sections


# ------------------------------------------------------------------ cable report
CABLE_REPORT = """Cable Report
Prepared By:,Test Author
On: ,06 Nov 2026 14:35:02
Splice Name:,TST-R0034
Location:,
Type:,FOSC 450B
,,,,,,Cable start reading:0,,Cable start reading:0,
,,FIBER CABLE 024 (2x12): {main},,FIBER CABLE 024 (2x12): {main},,FIBER CABLE 024 (2x12): {branch},,
Circuit ID,Port #,Fiber #,Color,Fiber #,Color,Fiber #,Color,Tray,Usage,Description (Address),Destination,Notes
"{main},1",3,01.01,blue/blue,01.01,blue/blue,,,Passthrough,Return,{u2},TST-R-200 MAIN ST,
"{branch},1",6,01.04,blue/brown,,,01.01,blue/blue,Unlocated,Return,{u1},TST-R-100 MAIN ST,
,4,,,01.04,blue/brown,,,,Broken,No Desc,TST-00037G,
"""


def _cable_report_region(folder: Path, *, branch_known: bool = True):
    main, branch = f"{ORIGIN} TO TST-00037G FC024", "TST-0034 TO TST-00040G FC024"
    pig = "TST-00040G TO TST-R-100 MAIN ST FC004"
    write_report(folder / "Splice_TST-00033G.xlsx", "TST-00033G", [
        (f"{main}: Seg3", 24, "Splice Case: TST-00033G", "Splice Case: TST-R0034", "Underground")], [])
    write_report(folder / "Splice_TST-00035.xlsx", "TST-00035", [
        (f"{main}: Seg4", 24, "Splice Case: TST-R0034", "Splice Case: TST-00035", "Underground")], [])
    if branch_known:
        write_report(folder / "Splice_TST-00040G.xlsx", "TST-00040G", [
            (f"{branch}: Seg1", 24, "Splice Case: TST-R0034", "Splice Case: TST-00040G", "Underground"),
            (f"{pig}: Seg1", 4, "Splice Case: TST-00040G", TERM.format(100), "Pigtail")],
            [_conn(cable_side(f"{branch}: Seg1", 1), cable_side(f"{pig}: Seg1", 1), U1, 100)])
    (folder / "Splice_TST-R0034_V1.csv").write_text(
        CABLE_REPORT.format(main=main, branch=branch, u1=U1, u2=U2), encoding="utf-8")
    return main


def test_cable_report_is_read(tmp_path):
    _cable_report_region(tmp_path)
    rep = read_report(tmp_path / "Splice_TST-R0034_V1.csv", load_config())
    assert rep.fmt == FMT_CABLE and rep.closure == "TST-R0034" and len(rep.connections) == 2
    c = rep.connections[1]
    assert (c.a.endpoint.fiber, c.b.endpoint.fiber, c.state, c.usage) == (4, 1, "Return", U1)
    assert (c.a.tube_color, c.a.fiber_color) == ("blue", "brown")


def test_cable_report_splices_are_traced(tmp_path):
    main = _cable_report_region(tmp_path)
    net = _net(tmp_path)
    assert "TST-R0034" in net.reports
    tr = net.trace("TST-00033G", CableFiber(main, 3, 4), U1)
    assert tr.stop == "terminal" and tr.last_closure == "TST-00040G"     # not the splice case TST-R0034
    assert net.connections_at("TST-R0034", (("C", main, 3, 1)))[0].b.endpoint.seg == 4   # pass-through


def test_cable_report_cable_without_segment_is_reported(tmp_path):
    _cable_report_region(tmp_path, branch_known=False)
    net = _net(tmp_path)
    assert any(i.code == "CABLE_REPORT_UNMAPPED" and "TST-0034 TO TST-00040G" in i.message for i in net.issues)


def test_unknown_layout_named_like_a_report_is_a_warning(tmp_path):
    (tmp_path / "Splice_TST-00077_V1.csv").write_text("Some Other Report\nfoo,bar\n", encoding="utf-8")
    (tmp_path / "notes.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _, issues = load_reports(sorted(tmp_path.glob("*.csv")), load_config())
    codes = {i.source: (i.severity, i.code) for i in issues}
    assert codes["Splice_TST-00077_V1.csv"] == ("WARNING", "REPORT_LAYOUT_UNKNOWN")
    assert codes["notes.csv"] == ("INFO", "NOT_A_SPLICE_REPORT")


# ------------------------------------------------------------------ same cable name twice
def test_two_cables_with_one_name_give_one_clear_warning(tmp_path):
    feed = f"{ORIGIN} TO TST-00039G FC096"
    mdu = "TST-00037 TO TST-R-NA OAK PL FC024"
    term = "FTTx MDU Enclosure: TST-R-NA OAK PL"
    conns = [_conn(cable_side(f"{feed}: Seg4", 33 + i), cable_side(f"{mdu}: Seg1", 1 + i),
                   f"TST-R-NA OAK PL:{i + 1} {i + 1} / NA OAK PL", 0) for i in range(3)]
    conns += [_conn(cable_side(f"{feed}: Seg4", 38 + i), cable_side(f"{mdu}: Seg1", 1 + i),
                    f"TST-R-NA OAK PL:{i + 1} {i + 1} / NA OAK PL", 0) for i in range(3)]
    write_report(tmp_path / "Splice_TST-00037.xlsx", "TST-00037", [
        (f"{feed}: Seg4", 96, "Splice Case: TST-00036G", "Splice Case: TST-00037", "Underground"),
        (f"{mdu}: Seg1", 24, "Splice Case: TST-00037", term, "Underground"),
        (f"{mdu}: Seg1", 24, "Splice Case: TST-00037", term, "Underground")], conns)
    net = _net(tmp_path)
    codes = [i.code for i in net.issues]
    assert codes.count("CABLE_NAME_REPEATED") == 1 and "FIBER_LISTED_TWICE" not in codes
    assert "fibres 1-3" in next(i.message for i in net.issues if i.code == "CABLE_NAME_REPEATED")

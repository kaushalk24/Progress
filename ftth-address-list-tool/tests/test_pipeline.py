import csv
import shutil

import openpyxl
import pytest

from ftth_addrlist.builder import Builder
from ftth_addrlist.config import ConfigError, load_config
from ftth_addrlist.model import APPROVED, CONFIRMED, PROVISIONAL, UNRESOLVED
from ftth_addrlist.network import Network
from ftth_addrlist.overrides import apply_overrides, load_overrides
from ftth_addrlist.pipeline import InputError, run
from ftth_addrlist.splice_reports import load_reports, read_report

from fixtures import CAB, FEEDER, HUB, OLM, POWER, build_network, cable_side, dev_side, usage, write_report


def build(folder, cfg=None):
    cfg = cfg or load_config()
    reps, issues = load_reports(sorted(folder.glob("*.xlsx")), cfg)
    net = Network(reps, cfg)
    return Builder(net, cfg).build(OLM), issues + net.issues


def row(res, cable, fiber):
    return next(r for r in res.rows if r.cable == cable and r.fiber == fiber)


@pytest.fixture
def net_dir(tmp_path):
    return build_network(tmp_path / "reports")


# ------------------------------------------------------------------ parsing
def test_report_parsing(net_dir):
    rep = read_report(net_dir / f"{HUB}.xlsx", load_config())
    assert rep.closure == HUB and rep.fmt == "connections_report"
    assert {(s.cable, s.seg) for s in rep.segments} == {(FEEDER, 1), (POWER, 1), (CAB, 1)}
    assert rep.devices[0].device_id == "PLCCOUPLER641" and rep.devices[0].index == 1 and rep.devices[0].count == 65
    assert len(rep.connections) == 8


# ------------------------------------------------------------------ rows and order
def test_sections_and_order(net_dir):
    res, _ = build(net_dir)
    assert res.hub == HUB
    assert [s[0] for s in res.sections] == [FEEDER, POWER, CAB]   # feeder, then by first PON port
    assert len(res.rows) == 24 + 4 + 12


def test_non_subscriber_rows(net_dir):
    res, _ = build(net_dir)
    assert row(res, FEEDER, 1).value("address") == f"{OLM} OLM TRANSPORT RETURN"
    assert row(res, FEEDER, 2).value("address") == f"{OLM} OLM TRANSPORT FORWARD"
    com = row(res, FEEDER, 5)
    assert com.value("address") == "PLC COUPLER 64 1 COM" and com.value("fiber_splice") == HUB
    spare = row(res, FEEDER, 9)
    assert spare.value("address") == "Spare (dark)" and spare.status == CONFIRMED
    assert spare.value("tube_color") == "BL" and spare.value("fiber_color") == "YL"
    pw = row(res, POWER, 1)
    assert (pw.value("pon_name"), pw.value("pon_port"), pw.value("address")) == ("1", 1, "POWER PORT")
    assert pw.value("tap_name") == "TST-R01-POWER TAP" and pw.value("fiber_splice") == HUB


def test_subscriber_confirmed_by_trace(net_dir):
    res, _ = build(net_dir)
    r = row(res, CAB, 3)
    assert (r.value("pon_name"), r.value("pon_port")) == ("1", 2)
    assert r.value("address") == "100 MAIN ST" and r.value("tap_name") == "TST-R-100 MAIN ST"
    assert r.value("fiber_splice") == "TST-00002" and r.fields["fiber_splice"].code == "FS-TRACE-TERMINAL"
    assert r.status == CONFIRMED
    assert "TST-00002.xlsx row" in "; ".join(r.fields["fiber_splice"].evidence)


def test_bridge_and_cable_end(net_dir):
    res, _ = build(net_dir)
    fs = row(res, CAB, 4).fields["fiber_splice"]
    assert fs.value == "TST-00010" and fs.code == "FS-CABLE-END" and fs.status == PROVISIONAL
    assert "no report" in row(res, CAB, 4).trace[0]


def test_break_point(net_dir):
    fs = row(build(net_dir)[0], CAB, 5).fields["fiber_splice"]
    assert fs.value == "TST-00003" and fs.code == "FS-BREAK-POINT" and fs.status == PROVISIONAL


def test_unknown_mid_cable_is_unresolved(net_dir):
    res, _ = build(net_dir)
    r = row(res, CAB, 6)
    assert r.value("fiber_splice") is None and r.status == UNRESOLVED
    assert any(i.code == "SPLICE_CLOSURE_UNKNOWN" for i in res.issues)
    assert not res.is_final


def test_accepted_rule_policy(net_dir):
    cfg = load_config()
    cfg["approvals"]["accepted_rules"] = ["FS-CABLE-END"]
    res, _ = build(net_dir, cfg)
    assert row(res, CAB, 4).fields["fiber_splice"].status == APPROVED
    assert row(res, CAB, 5).fields["fiber_splice"].status == PROVISIONAL


# ------------------------------------------------------------------ failure / conflict cases
def test_missing_folder(tmp_path):
    with pytest.raises(InputError):
        run(tmp_path / "nope", tmp_path / "out")


def test_empty_folder(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(InputError):
        run(tmp_path / "empty", tmp_path / "out")


def test_no_hub_report(tmp_path):
    d = build_network(tmp_path / "r", skip={"hub"})
    with pytest.raises(InputError):   # no OLM visible at all
        run(d, tmp_path / "out")
    res, _ = build(d)
    assert any(i.code == "NO_HUB" for i in res.issues) and not res.rows


def test_missing_column_reported(tmp_path):
    d = build_network(tmp_path / "r")
    write_report(d / "BROKEN.xlsx", "BROKEN", [], [{"a": cable_side(f"{CAB}: Seg1", 1),
                                                     "b": cable_side(f"{CAB}: Seg2", 1)}], drop_column="Usage")
    _, issues = build(d)
    bad = [i for i in issues if i.code == "REPORT_UNREADABLE"]
    assert bad and "Usage" in bad[0].message


def test_corrupt_file(tmp_path):
    d = build_network(tmp_path / "r")
    (d / "junk.xlsx").write_bytes(b"not a workbook")
    _, issues = build(d)
    assert any(i.code == "REPORT_UNREADABLE" for i in issues)


def test_duplicate_report(tmp_path):
    d = build_network(tmp_path / "r")
    shutil.copy(d / "TST-00002.xlsx", d / "TST-00002 (copy).xlsx")
    _, issues = build(d)
    assert any(i.code == "DUPLICATE_REPORT" for i in issues)


def test_duplicate_address_and_reused_port(tmp_path):
    extra = [{"a": dev_side("PLCCOUPLER641", 7), "b": cable_side(f"{CAB}: Seg1", 7), "usage": usage(100)},
             {"a": dev_side("PLCCOUPLER641", 7), "b": cable_side(f"{CAB}: Seg1", 8), "usage": usage(500)}]
    res, _ = build(build_network(tmp_path / "r", hub_extra=extra))
    codes = {i.code for i in res.issues}
    assert "DUPLICATE_ADDRESS" in codes and "PON_PORT_REUSED" in codes
    assert row(res, CAB, 7).fields["address"].status == PROVISIONAL


def test_tap_conflict(tmp_path):
    extra = [{"a": dev_side("PLCCOUPLER641", 9), "b": cable_side(f"{CAB}: Seg1", 9), "usage": usage(700),
              "start": "MAX10 Enclosure(M Bulk): TST-R-701 MAIN ST"}]
    res, _ = build(build_network(tmp_path / "r", hub_extra=extra))
    r = row(res, CAB, 9)
    assert r.value("tap_name") == "TST-R-701 MAIN ST" and r.fields["tap_name"].status == PROVISIONAL
    assert any(i.code == "TAP_CONFLICT" for i in res.issues)


def test_incomplete_connectivity(tmp_path):
    # TST-00004 exists but does not list fibre 6, while its predecessor segment is known: bridge impossible
    extra = [{"a": cable_side(f"{CAB}: Seg3", 6), "b": cable_side(f"{CAB}: Seg4", 6), "usage": usage(999)}]
    res, _ = build(build_network(tmp_path / "r", tst4_extra=extra))
    r = row(res, CAB, 6)
    assert r.status == UNRESOLVED   # downstream carries another premise: fibre cut somewhere, not resolvable


def test_circuit_conflict(tmp_path):
    d = build_network(tmp_path / "r")
    # hub says fibre 3 serves 100 MAIN ST; the next closure says 100 OAK ST on the same fibre
    write_report(d / "TST-00002.xlsx", "TST-00002", [
        (f"{CAB}: Seg1", 12, f"Splice Case: {HUB}", "Splice Case: TST-00002", "Underground"),
        (f"{CAB}: Seg2", 12, "Splice Case: TST-00002", "Splice Case: TST-00003", "Underground")],
        [{"a": cable_side(f"{CAB}: Seg1", 3), "b": cable_side(f"{CAB}: Seg2", 3),
          "usage": "TST-R-555 OAK ST:1 555 OAK ST"}])
    res, _ = build(d)
    assert row(res, CAB, 3).fields["fiber_splice"].status == UNRESOLVED
    assert any(i.code == "CIRCUIT_CONFLICT" for i in res.issues)


def test_segment_renumbering_between_reports(tmp_path):
    d = build_network(tmp_path / "r")
    # TST-00002 calls the span TST-00002..TST-00003 "Seg2"; give TST-00003 a report that calls it "Seg5"
    write_report(d / "TST-00003.xlsx", "TST-00003", [
        (f"{CAB}: Seg5", 12, "Splice Case: TST-00002", "Splice Case: TST-00003", "Underground"),
        (f"{CAB}: Seg3", 12, "Splice Case: TST-00003", "Splice Case: TST-00004", "Underground")],
        [{"a": cable_side(f"{CAB}: Seg5", 4), "b": cable_side(f"{CAB}: Seg3", 4), "usage": usage(200)}])
    res, _ = build(d)
    assert any(i.code == "SEGMENT_NUMBER_MISMATCH" for i in res.issues)
    assert row(res, CAB, 4).fields["fiber_splice"].value == "TST-00010"


def test_bad_config(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("[fiber_splice]\nmissing_report_policy = 'guess'\n")
    with pytest.raises(ConfigError):
        load_config(p)


# ------------------------------------------------------------------ overrides
def _ov(tmp_path, rows):
    p = tmp_path / "ov.csv"
    cols = ["olm", "cable_name", "fiber_no", "field", "action", "value", "approved_by", "approved_on", "reason",
            "expected_generated"]
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in cols}, **r})
    return p


def test_overrides(net_dir, tmp_path):
    res, _ = build(net_dir)
    ov, issues = load_overrides(_ov(tmp_path, [
        {"olm": OLM, "cable_name": CAB, "fiber_no": "6", "field": "Fiber Splice", "action": "SET", "value": "TST-00003",
         "approved_by": "J Smith", "approved_on": "2026-06-01", "reason": "field survey", "expected_generated": ""},
        {"olm": OLM, "cable_name": CAB, "fiber_no": "4", "field": "fiber_splice", "action": "ACCEPT",
         "value": "TST-00010", "approved_by": "J Smith", "approved_on": "2026-06-01", "reason": "cable end"},
        {"olm": OLM, "cable_name": CAB, "fiber_no": "5", "field": "fiber_splice", "action": "SET", "value": "X",
         "approved_by": "", "approved_on": ""},
        {"olm": OLM, "cable_name": CAB, "fiber_no": "3", "field": "fiber_splice", "action": "SET", "value": "Y",
         "approved_by": "A", "approved_on": "2026-06-01", "expected_generated": "OLDVALUE"},
    ]))
    assert not issues
    out = apply_overrides(res, ov)
    r6 = row(res, CAB, 6).fields["fiber_splice"]
    assert r6.value == "TST-00003" and r6.status == APPROVED and r6.code == "OVERRIDE"
    assert row(res, CAB, 4).fields["fiber_splice"].status == APPROVED
    codes = [i.code for i in out]
    assert "OVERRIDE_NOT_APPROVED" in codes            # fibre 5 not applied
    assert row(res, CAB, 5).fields["fiber_splice"].value == "TST-00003"
    assert "OVERRIDE_STALE" in codes and row(res, CAB, 3).fields["fiber_splice"].status == PROVISIONAL


def test_accept_of_unresolved_is_refused(net_dir, tmp_path):
    res, _ = build(net_dir)
    ov, _ = load_overrides(_ov(tmp_path, [
        {"olm": OLM, "cable_name": CAB, "fiber_no": "6", "field": "fiber_splice", "action": "ACCEPT", "value": "",
         "approved_by": "JS", "approved_on": "2026-06-01"},
        {"olm": OLM, "cable_name": CAB, "fiber_no": "6", "field": "fiber_splice", "action": "SET", "value": "",
         "approved_by": "JS", "approved_on": "2026-06-01"}]))
    codes = [i.code for i in apply_overrides(res, ov)]
    assert codes == ["OVERRIDE_ACCEPT_UNRESOLVED", "OVERRIDE_BLANK_WITHOUT_REASON"]
    assert row(res, CAB, 6).status == UNRESOLVED


def test_unknown_olm_fails_cleanly(net_dir, tmp_path):
    outs = run(net_dir, tmp_path / "out", olms=["TST-R99"], log=lambda *_: None)
    assert outs[0].workbook is None and outs[0].errors >= 1 and not outs[0].final


# ------------------------------------------------------------------ workbook output
def test_end_to_end_workbook(net_dir, tmp_path):
    out = tmp_path / "out"
    outs = run(net_dir, out, prefix="TEST", log=lambda *_: None)
    assert len(outs) == 1 and not outs[0].final
    wb_path = outs[0].workbook
    assert wb_path.name == "TEST_TST-R01_FTTH_Address List_DRAFT-REVIEW-REQUIRED.xlsx"
    wb = openpyxl.load_workbook(wb_path)
    assert wb.sheetnames == [OLM, "Row Status", "Field Evidence", "Exceptions", "Reports to Request", "Run Info"]
    ws = wb[OLM]
    assert [c.value for c in ws[1]] == ["PON NAME", "PON PORT", "FIBER #", "ADDRESS", "COLOR TUBE", "COLOR FIBER",
                                       "CABLE NAME", "Fiber Tap Name", "Fiber Splice"]
    assert ws.max_row == 41
    assert ws["A2"].value is None and ws["C2"].value == 1 and ws["G2"].value == FEEDER
    assert ws["A26"].value == 1 and ws["B26"].value == 1 and ws["D26"].value == "POWER PORT"
    assert ws["I2"].number_format == "@"
    assert wb["Run Info"]["B1"].value.startswith("DRAFT")
    # a second run never overwrites the first
    outs2 = run(net_dir, out, prefix="TEST", log=lambda *_: None)
    assert outs2[0].workbook != wb_path and wb_path.exists()
    assert outs[0].worklist.exists() and outs[0].exceptions_csv.exists()


def test_final_when_everything_resolved(tmp_path):
    d = build_network(tmp_path / "r")
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text('[approvals]\naccepted_rules = ["FS-CABLE-END", "FS-BREAK-POINT"]\n')
    ov = _ov(tmp_path, [{"olm": OLM, "cable_name": CAB, "fiber_no": "6", "field": "fiber_splice", "action": "SET",
                         "value": "TST-00003", "approved_by": "JS", "approved_on": "2026-06-01", "reason": "survey"}])
    outs = run(d, tmp_path / "out", config=cfg_path, overrides=ov, prefix="TEST", log=lambda *_: None)
    assert outs[0].final and "DRAFT" not in outs[0].workbook.name


def test_leading_zeros_preserved(tmp_path):
    d = tmp_path / "r"
    hub = "TST-00001G"
    cab = f"{hub} TO 00777 FC012"
    write_report(d / f"{hub}.xlsx", hub, [
        (f"{FEEDER}: Seg1", 24, f"OLM Housing: {OLM}", f"Splice Case: {hub}", "Underground"),
        (f"{cab}: Seg1", 12, f"Splice Case: {hub}", "Splice Case: 00777", "Underground")],
        [{"a": dev_side("PLCCOUPLER641", 2), "b": cable_side(f"{cab}: Seg1", 1), "usage": "TAP-01:1 0012 A ST"}],
        devices=[("PLC COUPLER 64 1 FE0-F1PLC64", 65)])
    outs = run(d, tmp_path / "out", log=lambda *_: None)
    ws = openpyxl.load_workbook(outs[0].workbook).worksheets[0]
    vals = {c.value for r in ws.iter_rows(min_row=2) for c in r}
    assert "0012 A ST" in vals and "00777" in vals


def test_address_lists_and_outputs_in_report_folder_are_ignored(net_dir, tmp_path):
    # a completed list and an earlier output kept with the reports must not count as unreadable reports
    out = net_dir / "out"
    first = run(net_dir, out, log=lambda *_: None)[0]
    shutil.copy(first.workbook, net_dir / "completed list.xlsx")
    second = run(net_dir, out, log=lambda *_: None)[0]
    assert second.errors == first.errors == 0
    _, issues = load_reports(sorted(net_dir.glob("*.xlsx")), load_config())
    assert any(i.code == "NOT_A_SPLICE_REPORT" and i.severity == "INFO" for i in issues)
    assert not any(i.code == "REPORT_UNREADABLE" for i in issues)


def test_output_file_names_are_valid_on_windows(net_dir, tmp_path):
    from ftth_addrlist.pipeline import safe_filename
    assert safe_filename('12/34: A<B>?_TST-R01_FTTH_Address List.xlsx') == "12-34- A-B--_TST-R01_FTTH_Address List.xlsx"
    oc = run(net_dir, tmp_path / "out", prefix="12/34: X", log=lambda *_: None)[0]
    assert oc.workbook.parent == tmp_path / "out" and ":" not in oc.workbook.name and "/" not in oc.workbook.name

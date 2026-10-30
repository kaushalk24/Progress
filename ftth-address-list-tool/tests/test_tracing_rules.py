"""Tracer and builder rules added after the second validation region (synthetic data)."""

from ftth_addrlist.builder import Builder
from ftth_addrlist.config import load_config
from ftth_addrlist.model import CONFIRMED, PROVISIONAL
from ftth_addrlist.network import Network
from ftth_addrlist.splice_reports import load_reports

from fixtures import CAB, HUB, OLM, build_network, cable_side, dev_side, usage


def build(folder, cfg=None):
    cfg = cfg or load_config()
    reps, issues = load_reports(sorted(folder.glob("*.xlsx")), cfg)
    return Builder(Network(reps, cfg), cfg).build(OLM)


def row(res, cable, fiber):
    return next(r for r in res.rows if r.cable == cable and r.fiber == fiber)


def test_remnant_with_same_usage_text_is_a_break_point(tmp_path):
    # TST-00004 lists fibre 6 with the SAME usage text, but as a cut piece: circuit TST-00003 -> TST-00010,
    # state 'Residential'. It must not be bridged; its circuit start is where the live fibre left the cable.
    extra = [{"a": cable_side(f"{CAB}: Seg3", 6), "b": cable_side(f"{CAB}: Seg4", 6), "usage": usage(400),
              "state": "Residential", "start": "Splice Case: TST-00003", "end": "Splice Case: TST-00010"}]
    fs = row(build(build_network(tmp_path / "r", tst4_extra=extra)), CAB, 6).fields["fiber_splice"]
    assert fs.value == "TST-00003" and fs.code == "FS-BREAK-POINT" and fs.status == PROVISIONAL


def test_same_circuit_origin_with_other_premise_continues(tmp_path):
    # Downstream report names 401 MAIN ST on the same fibre, but its circuit starts in our hub: the same
    # circuit (report revision). The trace continues; address and tap are flagged, not dropped.
    extra = [{"a": cable_side(f"{CAB}: Seg3", 6), "b": cable_side(f"{CAB}: Seg4", 6),
              "usage": "TST-R-401 MAIN ST:1 401 MAIN ST", "state": "Return",
              "start": "MAX10 Enclosure(M Bulk): TST-R-401 MAIN ST", "end": f"Splice Case: {HUB}"}]
    res = build(build_network(tmp_path / "r", tst4_extra=extra))
    r = row(res, CAB, 6)
    assert r.value("fiber_splice") == "TST-00010" and r.fields["fiber_splice"].status == PROVISIONAL
    assert r.value("address") == "400 MAIN ST" and r.fields["address"].code == "ADDR-VARIANT"
    codes = {i.code for i in res.issues}
    assert "DOWNSTREAM_PREMISE_DIFFERS" in codes and "CIRCUIT_CONFLICT" not in codes


def test_transport_hub_value_only_on_feeder_and_first_distribution(tmp_path):
    cab2 = f"{HUB} TO TST-00050 FC012"
    seg = [(f"{cab2}: Seg1", 12, f"Splice Case: {HUB}", "Splice Case: TST-00050", "Underground")]
    extra = [{"a": cable_side(f"{cab2}: Seg1", 1), "b": cable_side(f"{CAB}: Seg1", 12), "usage": "THROUGH FIBRE",
              "state": "Return"},
             {"a": dev_side("PLCCOUPLER641", 30), "b": cable_side(f"{cab2}: Seg1", 2), "usage": usage(900)}]
    d = build_network(tmp_path / "r", hub_extra=extra, hub_segments_extra=seg)
    res = build(d)
    assert [s[0] for s in res.sections][-1] == cab2
    assert row(res, CAB, 1).value("fiber_splice") == HUB            # first distribution section
    later = row(res, cab2, 1).fields["fiber_splice"]
    assert later.value is None and later.code == "FS-HUB-OMITTED" and later.status == CONFIRMED
    cfg = load_config()
    cfg["fiber_splice"]["hub_value_sections"] = "all"
    assert row(build(d, cfg), cab2, 1).value("fiber_splice") == HUB


def test_fibre_put_on_the_taps_own_cable(tmp_path):
    tap_cable = "TST-00002 TO TST-R-700 MAIN ST FC004"
    hub_extra = [{"a": dev_side("PLCCOUPLER641", 8), "b": cable_side(f"{CAB}: Seg1", 7), "usage": usage(700),
                  "start": "MAX10 Enclosure(M Bulk): TST-R-700 MAIN ST", "end": f"Splice Case: {HUB}"}]
    t2 = [{"a": cable_side(f"{CAB}: Seg1", 7), "b": cable_side(f"{tap_cable}: Seg1", 1), "usage": usage(700)}]
    t2_seg = [(f"{tap_cable}: Seg1", 4, "Splice Case: TST-00002", "", "Underground")]   # far end not recorded
    res = build(build_network(tmp_path / "r", hub_extra=hub_extra, tst2_extra=t2, tst2_segments_extra=t2_seg))
    fs = row(res, CAB, 7).fields["fiber_splice"]
    assert fs.value == "TST-00002" and fs.code == "FS-TAP-CABLE" and fs.status == PROVISIONAL


def test_address_quality_flags_keep_the_value(tmp_path):
    extra = [{"a": dev_side("PLCCOUPLER641", 9), "b": cable_side(f"{CAB}: Seg1", 8),
              "usage": "TST-R-800 MAIN ST:1 MAIN ST ST"},
             {"a": dev_side("PLCCOUPLER641", 10), "b": cable_side(f"{CAB}: Seg1", 9),
              "usage": "TST-R-810 MAIN ST:1 810 MAIN ST ST"}]
    res = build(build_network(tmp_path / "r", hub_extra=extra))
    no_num = row(res, CAB, 8).fields["address"]
    assert no_num.value == "MAIN ST ST" and no_num.code == "ADDR-NO-NUMBER" and no_num.status == PROVISIONAL
    repeated = row(res, CAB, 9).fields["address"]
    assert repeated.value == "810 MAIN ST ST" and repeated.status == CONFIRMED
    codes = [i.code for i in res.issues]
    assert "ADDRESS_NO_NUMBER" in codes and codes.count("ADDRESS_REPEATED_WORD") == 2


def test_route_lists_bridged_closures(tmp_path):
    r = row(build(build_network(tmp_path / "r")), CAB, 4)
    assert r.route == [HUB, "TST-00002", "TST-00003", "TST-00004", "TST-00010"]   # ends at the stop
    assert r.trace_end["stop"] == "missing_report" and r.trace_end["at"] == "TST-00010"

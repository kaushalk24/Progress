"""Rules derived from the forensic analysis of the approved designs (see FORENSIC_FINDINGS.md)."""
import json
from pathlib import Path

from fttx_bom.engine import policies as pol
from fttx_bom.engine.doctor import ped_cable_roles, run_doctor
from fttx_bom.engine.network import GRANT, NONGRANT
from fttx_bom.engine.rules import Rule
from fttx_bom.engine.takeoff import CableSegment, Takeoff, ground_locations, grounding_points
from fttx_bom.excel.reports import Reference
from fttx_bom.extract.model import Drawing, Insert

CONV = json.loads((Path(__file__).resolve().parents[1] / "config" / "conventions.json").read_text())
NET = "N-R01"


class FakeClassifier:
    """Everything is in N-R01; x >= 1000 is Non-Grant."""
    nearest_assigned: list = []
    tolerance = 0.0
    networks: dict = {}
    notes: list = []
    nongrant: list = []

    def network_of(self, p, what="", strict=False):
        return NET

    def area_of(self, p):
        return NONGRANT if p[0] >= 1000 else GRANT


def _spl(name, x, y):
    return Insert(handle=name, name="MC_SPLICE.dwg", layer="CX1-SPLICE", pt=(x, y), attribs={"NAME": name})


def _cab(a, b, fib, path):
    return CableSegment(handle=f"{a}-{b}", name=f"{a} TO {b} FC{fib:03d}", a=a, b=b, fibers=fib, placement="UG",
                        route_ft=1, slack_ft=0, total_ft=1, network=NET, path=path)


def _design():
    """OLM -> hub N-01001G -> 96F feeder through N-01002, N-01003, N-01010 to N-01004G; 24F branch N-01003 -> N-01005."""
    d = Drawing("t", "test")
    d.inserts = [Insert("olm", "CX1_OLM", "OLM", (0, -100)),
                 _spl("N-01001G", 0, 0), _spl("N-01002", 100, 0), _spl("N-01003", 200, 0),
                 _spl("N-01010", 300, 0), _spl("N-01004G", 1400, 0), _spl("N-01005", 200, 100)]
    tk = Takeoff([NET])
    tk.cables = [_cab("N-01001G", "N-01004G", 96, [(0, 0), (100, 0), (200, 0), (300, 0), (1400, 0)]),
                 _cab("N-01003", "N-01005", 24, [(200, 0), (200, 100)])]
    return d, tk


def test_ground_locations_follow_template_note():
    d, tk = _design()
    reasons, _pts, hubs = ground_locations(d, CONV, tk)
    assert hubs == {"N-01001G"}  # splice nearest the OLM block
    assert reasons["N-01001G"] == {"G suffix"}
    assert reasons["N-01002"] == {"first in line"}  # first splice on the hub cable's routed path, not its B end
    assert reasons["N-01010"] == {"ends in 0"}
    assert reasons["N-01004G"] == {"G suffix", "end of line"}
    assert reasons["N-01005"] == {"end of line"}
    assert "N-01003" not in reasons  # a branch splice is not on the note's list


def test_ground_kit_policy_options():
    d, tk = _design()
    grounding_points(d, CONV, FakeClassifier(), tk)
    assert tk.get("grounding_points", NET, GRANT) == 4 and tk.get("grounding_points", NET, NONGRANT) == 1  # counted once each
    pol.compute_variants(tk)
    pol.apply(tk, {})
    assert tk.policy_used["ground_kits"] == "template_note" and tk.get("grounding_points", NET, GRANT) == 4
    pol.apply(tk, {"ground_kits": "g_suffix"})
    assert (tk.get("grounding_points", NET, GRANT), tk.get("grounding_points", NET, NONGRANT)) == (1, 1)
    pol.apply(tk, {"ground_kits": "not_ordered"})
    assert tk.get("grounding_points", NET, GRANT) == 0


def test_ground_kits_warn_without_hub():
    d, tk = _design()
    d.inserts[0].pt = (5000, 5000)  # OLM far from every splice point
    grounding_points(d, CONV, FakeClassifier(), tk)
    assert any(c.name == "ground kits: OLM hub" and c.status == "WARN" for c in tk.checks)


def test_calibrate_skips_rows_blank_in_reference():
    # regression: a line the approved BOM never filled in was scored as if it said 0
    d, tk = _design()
    grounding_points(d, CONV, FakeClassifier(), tk)
    pol.compute_variants(tk)
    pol.apply(tk, {})
    rule = Rule("FE0-07264810", None, "grounding_points", "EA", "INFERRED", True, "", "")
    cols = {(NET, GRANT): "H", (NET, NONGRANT): "I"}
    blank = Reference("ref", columns=cols, values={rule.key: {(NET, GRANT): None, (NET, NONGRANT): None}})
    assert not [r for r in pol.calibrate(tk, [rule], blank) if r["policy"] == "ground_kits"]
    filled = Reference("ref", columns=cols, values={rule.key: {(NET, GRANT): 1, (NET, NONGRANT): None}})
    rows = [r for r in pol.calibrate(tk, [rule], filled) if r["policy"] == "ground_kits"]
    assert next(r for r in rows if r["best"])["option"] == "g_suffix"


def _peds_design(ped_block):
    d = Drawing("t", "test")
    d.inserts = [_spl("N-01001", 0, 0), _spl("N-01002", 500, 0), _spl("N-01003", 900, 0),
                 Insert("p", ped_block, "PEDS", (500, 30))]
    tk = Takeoff([NET])
    tk.cables = [_cab("N-01001", "N-01003", 96, [(0, 0), (500, 0), (900, 0)])]  # N-01002 is mid-span on a 96F cable
    return d, tk


def test_ped_cable_roles_mid_span():
    d, tk = _peds_design("CX1-MAX5")
    [(ped, nm, role, fib)] = ped_cable_roles(d, CONV, tk)
    assert (nm, role, fib) == ("N-01002", "pass", 96)


def test_doctor_flags_max5_mid_span_on_large_cable():
    d, tk = _peds_design("CX1-MAX5")
    issues = run_doctor(d, CONV, FakeClassifier(), tk, {}, [])
    hit = [i for i in issues if i.code == "MAX5_ON_LARGE_CABLE"]
    assert len(hit) == 1 and hit[0].severity == "WARN" and hit[0].x == 500
    d, tk = _peds_design("CX1-MAX10")
    assert not [i for i in run_doctor(d, CONV, FakeClassifier(), tk, {}, []) if i.code.startswith("MAX")]


# ---- network boundaries (code review BLOCKER 2 / MAJOR 3) ----------------------------------
from fttx_bom.engine.network import build_classifier  # noqa: E402
from fttx_bom.extract.model import Polyline, Text  # noqa: E402

SQUARE = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]


def _boundary(handle, dx=0, label=None):
    pl = Polyline(handle, CONV["network_boundary_layers"][0], [(x + dx, y) for x, y in SQUARE], True)
    txt = [Text("t" + handle, CONV["network_label_layers"][0], label, (500 + dx, 500))] if label else []
    return pl, txt


def _drawing(*bounds):
    d = Drawing("t", "test")
    for pl, txt in bounds:
        d.polylines.append(pl)
        d.texts += txt
    return d


def test_unrecognised_label_is_an_error_not_whole_drawing():
    d = _drawing(_boundary("a", 0, "NMK R02"), _boundary("b", 5000, "NMK R03"))  # labels the regex does not match
    cls = build_classifier(d, CONV, ["NMK-R02"])
    assert cls.single_network is None and cls.network_of((6000, 500)) is None
    assert any("no DWG boundary polygon found" in n for n in cls.notes)


def test_single_unlabelled_boundary_used_with_warning():
    d = _drawing(_boundary("a", 0, None))
    cls = build_classifier(d, CONV, ["X-R01"])
    assert cls.network_of((500, 500)) == "X-R01" and cls.network_of((5000, 5000)) is None
    assert any(n.startswith("boundary fallback") for n in cls.notes)


def test_no_boundaries_counts_everything_with_warning():
    cls = build_classifier(_drawing(), CONV, ["X-R01"])
    assert cls.network_of((123, 456)) == "X-R01"
    assert any(n.startswith("boundary fallback") for n in cls.notes)


def test_foreign_network_objects_excluded():
    d = _drawing(_boundary("a", 0, "NMK-R02"), _boundary("b", 1100, "NMK-R03"))
    cls = build_classifier(d, CONV, ["NMK-R02"])
    assert sorted(cls.foreign) == ["NMK-R03"]
    assert cls.network_of((1500, 500)) is None and cls.foreign_of((1500, 500)) == "NMK-R03"
    assert cls.network_of((1080, 500)) is None  # 80 ft outside R02 but 20 ft from R03: nearest is the other network
    assert cls.network_of((1020, 500)) == "NMK-R02"
    assert not cls.unassigned and len(cls.foreign_assigned) == 2


def test_transport_network_without_boundary_does_not_crash():
    # regression (code review MAJOR 3): KeyError when the OTN-fed network has no boundary polygon
    d = _drawing(_boundary("a", 0, "NMK-R02"))
    d.polylines.append(Polyline("tr", CONV["transport_boundary_layers"][0], [(2000, 0), (3000, 0), (3000, 100), (2000, 100)], True))
    d.inserts.append(Insert("lbl", CONV["blocks"]["cable_label"]["names"][0], "x", (2500, 50),
                            attribs={"SEGNUM": "NMK-NEW MARKET MN OTN TO NMK-04034 FC072"}))
    cls = build_classifier(d, CONV, ["NMK-R02", "NMK-R04"])
    assert cls.transport_network == "NMK-R04"
    assert cls.network_of((2500, 50)) == "NMK-R04"  # corridor still feeds R04 although R04 has no boundary; no crash
    assert build_classifier(d, CONV, ["NMK-R02"]).network_of((2500, 50)) is None  # R04 not in the job: corridor excluded


def test_closure_over_capacity_flagged():
    # FOSC 450 ordering guide: a 450D with the tall basket holds 5 trays (240 splices at 48/tray), a 450B 6 (144)
    d = Drawing("t", "test")
    tk = Takeoff([NET])
    tk.extra["enclosures"] = [(NET, GRANT, "D", 255, "N-01001G"), (NET, GRANT, "D", 240, "N-01002"),
                              (NET, GRANT, "B", 145, "N-01003")]
    hits = [i for i in run_doctor(d, CONV, FakeClassifier(), tk, {}, []) if i.code == "CLOSURE_OVER_CAPACITY"]
    assert sorted(i.message.split(":")[0] for i in hits) == ["N-01001G", "N-01003"]

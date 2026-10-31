"""Integration / regression tests on the real project files.

Set FTTX_TEST_DATA to a folder laid out as:
  dwg/386106_Credit_River_MN_FTTH_Combined_DWG.dwg
  dwg/386021_MelcherDallas_BEAD_FTTH_DMI-R15_DWG.dwg
  addr/Address List/*.xlsx                (NMK-R02..R05)
  splice/Splice Reports/                  (NMK splice reports)
  bom/386106_Credit River MN_FTTH_Combined_BOM.xlsx
  dmi/386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx
  dmi/splice/                             (DMI splice reports)
Expected values below come from the manual NMK BOM where independent sources
(drawing + address list + splice reports) agree with it.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fttx_bom.engine.network import GRANT, NONGRANT, build_classifier
from fttx_bom.engine.rules import CONFIG_DIR
from fttx_bom.engine.takeoff import build_takeoff
from fttx_bom.extract.backends import load_drawing
from fttx_bom.inputs.address_list import read_address_lists
from fttx_bom.inputs.splice_reports import read_splice_reports

DATA = Path(os.environ.get("FTTX_TEST_DATA", "/nonexistent"))
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="FTTX_TEST_DATA not set (project files not available)")
CONV = json.loads((CONFIG_DIR / "conventions.json").read_text())
NETS = ["NMK-R02", "NMK-R03", "NMK-R04", "NMK-R05"]


@pytest.fixture(scope="module")
def nmk(tmp_path_factory):
    d = load_drawing(DATA / "dwg/386106_Credit_River_MN_FTTH_Combined_DWG.dwg", tmp_path_factory.mktemp("cache"))
    als = read_address_lists(sorted((DATA / "addr/Address List").glob("*.xlsx")))
    reps = read_splice_reports([DATA / "splice/Splice Reports"])
    cls = build_classifier(d, CONV, NETS)
    return d, cls, build_takeoff(d, CONV, cls, NETS, als, reps)


@pytest.fixture(scope="module")
def dmi(tmp_path_factory):
    d = load_drawing(DATA / "dwg/386021_MelcherDallas_BEAD_FTTH_DMI-R15_DWG.dwg", tmp_path_factory.mktemp("cache"))
    als = read_address_lists([DATA / "dmi/386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx"])
    reps = read_splice_reports([DATA / "dmi/splice"])
    cls = build_classifier(d, CONV, ["DMI-R15"])
    return d, cls, build_takeoff(d, CONV, cls, ["DMI-R15"], als, reps)


def cols(tk, key):
    return [tk.get(key, n, a) for n in NETS for a in (GRANT, NONGRANT)]


def nettot(tk, key):
    return [tk.total(key, n) for n in NETS]


# ---- extraction ---------------------------------------------------------------
def test_extraction_counts(nmk):
    d, cls, _tk = nmk
    assert d.census["INSERT"] == 8490 and d.census["ATTRIB"] == 39842
    assert len(d.inserts_named("CX1-MAX5")) == 593 and len(d.inserts_named("CX1-MAX10")) == 260
    assert sorted(cls.networks) == NETS
    assert len(cls.nongrant) == 166  # 163 proxy LWPolygons + 3 LWPOLYLINEs
    assert not any("CRITICAL" in w for w in d.warnings)


# ---- passings (reference rows 13-15, all 24 cells) ----------------------------
def test_passings_match_reference(nmk):
    tk = nmk[2]
    assert cols(tk, "pass_res") == [17, 210, 29, 201, 33, 176, 95, 83]
    assert cols(tk, "pass_com") == [0, 2, 2, 10, 0, 3, 4, 3]
    assert cols(tk, "pass_mdu") == [0, 0, 0, 4, 0, 4, 4, 0]


def test_passings_equal_address_lists(nmk):
    assert all(c.status == "PASS" for c in nmk[2].checks if c.name.startswith("passings vs address list"))


# ---- structures ----------------------------------------------------------------
def test_peds_and_vaults(nmk):
    tk = nmk[2]
    assert nettot(tk, "ped_max10") == [59, 51, 80, 70]
    assert nettot(tk, "ped_max5") == [147, 183, 136, 127]
    assert cols(tk, "ped_max10")[0:2] == [55, 4] and cols(tk, "ped_max10")[4:8] == [63, 17, 70, 0]
    # transport-corridor vault belongs to NMK-R04 (regression: was unassigned)
    assert nettot(tk, "vault") == [2, 3, 5, 9]
    assert cols(tk, "vault")[4:6] == [4, 1]


def test_olm_and_power(nmk):
    tk = nmk[2]
    assert cols(tk, "olm") == [1, 0, 1, 0, 1, 0, 1, 0]
    assert cols(tk, "olm_ground") == [1, 0, 1, 0, 1, 0, 1, 0]
    assert cols(tk, "mdu_buildings") == [0, 0, 0, 1, 0, 1, 1, 0]


def test_splitters_and_sfp(nmk):
    tk = nmk[2]
    assert cols(tk, "splitter_1x64") == [1, 3, 1, 3, 1, 3, 2, 1]
    # SME rule (Melcher-Dallas BOM): Non-Grant = ROUNDUP(NG/64), Grant = ROUNDUP(total/64) - Non-Grant
    assert cols(tk, "pon_ports") == [0, 4, 0, 4, 1, 3, 1, 2]
    assert sum(cols(tk, "pon_ports")) == 15 == sum(tk.extra["designed_pons"].values())  # one SFP per designed PON
    assert cols(tk, "pon_ports@jumper_half") == [1, 4, 1, 4, 1, 3, 2, 2]  # Credit River BOM: rounded per column (18)
    assert all(c.status == "PASS" for c in tk.checks if c.name.startswith("splitters vs"))


def test_enclosures(nmk):
    tk = nmk[2]
    assert nettot(tk, "fosc450d") == [2, 2, 2, 4]
    assert nettot(tk, "fosc450b") == [0, 1, 1, 3]
    assert cols(tk, "fosc450b")[5] == 1  # NMK-04073 is Non-Grant, as in the reference


def test_splice_trays_sme_rule(nmk):
    # SME: trays per location ROUNDUP(splices/48 or /24); 2-tray packages pooled per column.
    # Reproduces reference 450D R02 4, R04 4, R05 5 (R03 5 vs 4) and 450B 1/1/2 exactly.
    tk = nmk[2]
    assert nettot(tk, "trays_450d") == [7, 9, 7, 9]
    assert nettot(tk, "tray_450d") == [4, 5, 4, 5]
    assert nettot(tk, "tray_450b") == [0, 1, 1, 2]


def test_drops_fx_drops_lines(nmk):
    # FX_DROPS drop lines exist for R03 and R05 only; R03 Non-Grant reproduces the reference (52,678) within 0.2%
    tk = nmk[2]
    assert tk.get("drop_ft", "NMK-R03", NONGRANT) == pytest.approx(52678, rel=0.002)
    assert ("drop_ft_bom", "NMK-R02", NONGRANT) not in tk.q  # no drops drawn -> not computed, never 0
    assert any(c.name == "drops vs passings NMK-R03" and c.status == "PASS" for c in tk.checks)


def test_max10_upgrades_need_based(nmk):
    tk = nmk[2]
    assert max(tk.get("ped_ports_max", n, a) for n in NETS for a in (GRANT, NONGRANT)) <= 4
    assert nettot(tk, "max10_upgrades@need_based") == [0, 0, 0, 0]
    # default = blank-template formula (one kit per Non-Grant MAX10), as in the approved Melcher-Dallas BOM
    assert cols(tk, "max10_upgrades") == [0 if a == GRANT else tk.get("ped_max10", n, a) for n in NETS for a in (GRANT, NONGRANT)]


# ---- cable --------------------------------------------------------------------
def test_cable_network_totals(nmk):
    tk = nmk[2]
    assert nettot(tk, "cable_024") == [45490, 48019, 34686, 60167]  # labels + 100 ft OLM tail
    assert nettot(tk, "cable_048") == [8471, 33245, 15285, 12994]
    assert nettot(tk, "cable_072") == [0, 6505, 19143, 7859]  # R04 includes the 9,040 ft OTN transport
    assert nettot(tk, "cable_096") == [10616, 5364, 0, 8507]
    assert nettot(tk, "cable_144") == [11965, 6983, 20853, 14280]


def test_cable_span_split_regression(nmk):
    # span-based allocation reproduces the reference R03 FC048 split exactly
    tk = nmk[2]
    assert (tk.get("cable_048", "NMK-R03", GRANT), tk.get("cable_048", "NMK-R03", NONGRANT)) == (23785, 9460)


def test_cable_labels_agree_with_splice_reports(nmk):
    tk = nmk[2]
    assert not [c for c in tk.checks if c.name == "cable label vs splice report"]
    tails = [c for c in tk.checks if c.name == "cable missing DWG label"]
    assert len(tails) == 4  # one 100 ft OLM tail per network, flagged


def test_no_failed_checks_nmk(nmk):
    assert [c for c in nmk[2].checks if c.status == "FAIL"] == []


# ---- DMI-R15 (no reference BOM: internal consistency) ---------------------------
def test_dmi_internal_consistency(dmi):
    _d, _cls, tk = dmi
    n = "DMI-R15"
    assert tk.total("passings", n) == 222
    assert tk.get("pass_res", n, GRANT) == 67  # all GRANTADDRESS blocks served (incl. unnumbered)
    assert tk.total("pass_com", n) == 13
    assert tk.total("splitter_1x32", n) == 7 and tk.total("splitter_1x64", n) == 0  # design uses 1x32
    # SME rule (approved DMI BOM): Non-Grant ROUNDUP(155/64) = 3, Grant ROUNDUP(222/64) - 3 = 1
    assert (tk.get("pon_ports", n, GRANT), tk.get("pon_ports", n, NONGRANT)) == (1, 3)
    assert any(c.name == f"SFP vs designed PONs {n}" and c.status == "WARN" for c in tk.checks)
    assert tk.total("olm", n) == 1
    assert [c for c in tk.checks if c.status == "FAIL"] == []


def test_dmi_drops(tmp_path_factory):
    p = DATA / "dwg/386021_MelcherDallas_BEAD_FTTH_DMI-R15_DWG_drops.dwg"
    if not p.exists():
        pytest.skip("drop-run DMI drawing not supplied")
    d = load_drawing(p, tmp_path_factory.mktemp("cache"))
    als = read_address_lists([DATA / "dmi/386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx"])
    cls = build_classifier(d, CONV, ["DMI-R15"])
    tk = build_takeoff(d, CONV, cls, ["DMI-R15"], als, read_splice_reports([DATA / "dmi/splice"]))
    assert tk.total("drop_count", "DMI-R15") == 222  # one drop per served (non-MDU) address
    assert tk.total("drop_ft", "DMI-R15") == pytest.approx(36117, abs=5)  # = sum of CX1-FTG-N2 drop labels


@pytest.mark.slow
def test_cli_end_to_end_dmi(tmp_path):
    cmd = [sys.executable, "-m", "fttx_bom", "--dwg", str(DATA / "dwg/386021_MelcherDallas_BEAD_FTTH_DMI-R15_DWG.dwg"),
           "--address-list", str(DATA / "dmi/386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx"),
           "--splice-reports", str(DATA / "dmi/splice"), "--template", str(DATA / "bom/386106_Credit River MN_FTTH_Combined_BOM.xlsx"),
           "--out", str(tmp_path)]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=1800)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (tmp_path / "386021_DMI-R15_FINAL_BOM.xlsx").exists()
    assert (tmp_path / "386021_DMI-R15_BOM_AUDIT.xlsx").exists()
    assert "workbook  : FAIL=0" in p.stdout and "deep check: ERROR=0" in p.stdout


def test_deep_check_real_findings(nmk):
    from fttx_bom.engine.doctor import run_doctor

    d, cls, tk = nmk
    als = read_address_lists(sorted((DATA / "addr/Address List").glob("*.xlsx")))
    reps = read_splice_reports([DATA / "splice/Splice Reports"])
    issues = run_doctor(d, CONV, cls, tk, als, reps)
    codes = {i.code for i in issues}
    assert not [i for i in issues if i.severity == "ERROR"]
    assert any(i.code == "SERVED_NOT_DRAWN" and "2595 PILLSBURY" in i.message for i in issues)  # address-list typo of 22595
    assert {"ADDRESS_DUPLICATE", "CABLE_ONLY_IN_REPORT", "DROP_COUNT_MISMATCH", "SPLICE_GUIDE_FORMAT"} <= codes
    assert len(issues) < 150  # noise guard: actionable list, not thousands of lines


def test_single_olm_run_equals_combined_run(nmk):
    # regression (code review BLOCKER): a per-OLM job on the combined drawing booked neighbouring networks'
    # objects within 150 ft, the whole transport corridor and inter-network cables to the job network
    d, _cls, tk4 = nmk
    als = read_address_lists(sorted((DATA / "addr/Address List").glob("*.xlsx")))
    for n in NETS:
        reps = read_splice_reports([DATA / "splice/Splice Reports"])
        cls1 = build_classifier(d, CONV, [n])
        assert sorted(cls1.foreign) == [x for x in NETS if x != n]
        tk1 = build_takeoff(d, CONV, cls1, [n], {n: als[n]}, reps, policies={})
        keys = {k for k, nn, _a in tk4.q if nn == n and "@" not in k} | {k for k, nn, _a in tk1.q if nn == n and "@" not in k}
        diff = [(k, a, tk4.get(k, n, a), tk1.get(k, n, a)) for k in sorted(keys) for a in (GRANT, NONGRANT)
                if abs((tk4.get(k, n, a) or 0) - (tk1.get(k, n, a) or 0)) > 0.01]
        assert not diff, (n, diff[:5])


def test_ground_kits_template_note(nmk, dmi):
    tk = nmk[2]
    assert cols(tk, "grounding_points") == [19, 51, 23, 62, 21, 66, 56, 23]
    first = sorted(nm for _n, _a, nm, why in tk.extra["ground"] if "first in line" in why)
    assert first == ["NMK-02002", "NMK-02119", "NMK-02120", "NMK-03002", "NMK-03092", "NMK-03129",
                     "NMK-04002", "NMK-04117", "NMK-04217", "NMK-05002", "NMK-05117"]
    assert dmi[2].total("grounding_points", "DMI-R15") == 126


def test_ped_size_design_rule(nmk, dmi):
    # forensic finding F1: no MAX5 houses a splice on a cable above 48F in either approved design
    from fttx_bom.engine.doctor import ped_cable_roles

    for d, _cls, tk in (nmk, dmi):
        closures = {e[4].upper() for e in tk.extra["enclosures"]}  # FOSC 450 splices are not ped splices
        roles = ped_cable_roles(d, CONV, tk, closures)
        assert not [1 for ped, _n, role, fib in roles if ped.name == "CX1-MAX5" and fib > 48]  # any role, closures excluded
        assert sum(1 for ped, _n, role, fib in roles if ped.name == "CX1-MAX10" and role == "pass" and fib > 48) >= 11


def test_d_basket_zero_with_t3v_closure(nmk):
    # the T3V 450D includes its tall basket; the approved BOM orders 0 D baskets
    tk = nmk[2]
    assert cols(tk, "basket_d") == [0] * 8


def test_mixed_split_ratios_written(dmi):
    # code review MAJOR 5: a second split ratio was written as 0 with every check passing
    d, cls, _tk = dmi
    als = read_address_lists([DATA / "dmi/386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx"])
    reps = read_splice_reports([DATA / "dmi/splice"])
    next(r for r in reps if r.name == "DMI-15008G").couplers += [(64, "FE0-F1PLC64"), (64, "FE0-F1PLC64")]
    tk = build_takeoff(d, CONV, cls, ["DMI-R15"], als, reps, policies={})
    assert tk.total("splitter_1x64", "DMI-R15") == 2 and tk.total("splitter_1x32", "DMI-R15") == 7
    assert any(c.name.startswith("mixed split ratios") and c.status == "WARN" for c in tk.checks)


def test_no_splice_reports_leaves_enclosures_blank(dmi):
    # code review MAJOR 11(a): FOSC 450B/D were written as 0 without splice reports
    d, cls, _tk = dmi
    als = read_address_lists([DATA / "dmi/386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx"])
    tk = build_takeoff(d, CONV, cls, ["DMI-R15"], als, [], policies={})
    assert not [k for k in tk.q if k[0].startswith(("fosc450", "tray_450", "trays_450"))]


def test_cable_cells_sum_to_rounded_total(nmk):
    # code review MINOR 19: separately rounded Grant / Non-Grant cells could lose 1 ft
    tk = nmk[2]
    for n in NETS:
        for fc in sorted({c.fibers for c in tk.cables if c.network == n}):
            want = round(sum(c.total_ft for c in tk.cables if c.network == n and c.fibers == fc))
            assert tk.get(f"cable_{fc:03d}", n, GRANT) + tk.get(f"cable_{fc:03d}", n, NONGRANT) == want, (n, fc)


def test_template_capacity_counts_transport_columns():
    # code review MAJOR 9: a 2-OLM job on the blank per-OLM template lost the second OLM's Transport BOM
    from fttx_bom.engine.rules import load_rules
    from fttx_bom.excel.writer import template_capacity

    cfg, _ = load_rules()
    tpl = next((DATA / "template2").glob("*.xlsx"), None)
    if tpl is None:
        pytest.skip("blank template not in FTTX_TEST_DATA/template2")
    assert template_capacity(tpl, cfg) == 2  # 4 main columns but 2 Transport BOM columns -> one OLM per BOM
    assert template_capacity(DATA / "bom/386106_Credit River MN_FTTH_Combined_BOM.xlsx", cfg) == 8


def test_dmi_rf_plant_excluded(dmi):
    # approved Melcher-Dallas BOM: RF (coax) support structures are not calculated
    _d, _cls, tk = dmi
    n = "DMI-R15"
    assert (tk.get("vault", n, GRANT), tk.get("vault", n, NONGRANT)) == (7, 1)  # 9 drawn, 1 at the RF amplifier
    assert tk.total("route_aerial_ft", n) == 0  # 512 ft strand carries no fiber
    rf = {k for k, *_x in tk.extra["rf_structures"]}
    assert rf == {"vault", "route_aerial_ft"}


def test_dmi_duplicate_cable_label_counted_once(dmi):
    # the approved BOM summed both labels of 'DMI-14001G TO DMI-15204G FC024' (6,467 ft twice)
    _d, _cls, tk = dmi
    assert tk.total("cable_024", "DMI-R15") == 140644  # = splice reports
    assert any(c.name == "duplicate cable label" and "DMI-14001G TO DMI-15204G" in c.detail for c in tk.checks)


def test_dmi_approved_bom_reconciliation(dmi):
    from fttx_bom.engine.rules import load_rules
    from fttx_bom.excel.reports import read_reference

    path = DATA / "dmi_ref/386021_MelcherDallas_BEAD_FTTH_DMI-R15_BOM.xlsx"
    if not path.exists():
        pytest.skip("approved DMI-R15 BOM not in FTTX_TEST_DATA/dmi_ref")
    cfg, rules = load_rules()
    ref = read_reference(path, cfg["sheet"], rules)  # sheet is named "OLM DMI-R15 BOM"
    tk = dmi[2]
    want = {"FM0-3FE47548AD": "pon_ports", "FE0-F1PLC32": "splitter_1x32", "CBV-HGIB2436": "vault",
            "FE0-MAX10EXP4": "max10_upgrades", "CBP-MAX10DSM24": "ped_max10", "Residential Count": "pass_res"}
    for part, key in want.items():
        for a in (GRANT, NONGRANT):
            assert (ref.values[part][("DMI-R15", a)] or 0) == tk.get(key, "DMI-R15", a), (part, a)


def test_splice_guide_format_parsed():
    reps = read_splice_reports([DATA / "splice/Splice Reports/NMK-R03/NMK-03129.xlsx"])
    r = reps[0]
    assert (r.name, r.format, r.fusion_splices, r.pass_through) == ("NMK-03129", "splice guide", 10, 134)

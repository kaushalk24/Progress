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
    assert cols(tk, "pon_ports") == [1, 4, 1, 4, 1, 3, 2, 2]
    assert all(c.status == "PASS" for c in tk.checks if c.name.startswith("splitters vs"))


def test_enclosures(nmk):
    tk = nmk[2]
    assert nettot(tk, "fosc450d") == [2, 2, 2, 4]
    assert nettot(tk, "fosc450b") == [0, 1, 1, 3]
    assert cols(tk, "fosc450b")[5] == 1  # NMK-04073 is Non-Grant, as in the reference


def test_splice_trays_sme_rule(nmk):
    # SME walkthrough: per location ROUNDUP(ROUNDUP(splices/48)/2); R02 and R04 reproduce the reference "3+1"
    tk = nmk[2]
    assert nettot(tk, "tray_450d") == [4, 5, 4, 6]
    assert nettot(tk, "tray_450b") == [0, 1, 1, 3]


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
    # SME rule: SFP = ROUNDUP(ROUNDUP(p/32)/2) per column -> 2 + 3 = 5 for 7 designed 1x32 PONs, flagged
    assert tk.total("pon_ports", n) == 5
    assert any(c.name == f"SFP vs designed PONs {n}" and c.status == "WARN" for c in tk.checks)
    assert tk.total("olm", n) == 1
    assert [c for c in tk.checks if c.status == "FAIL"] == []


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
    assert "workbook FAIL=0" in p.stdout

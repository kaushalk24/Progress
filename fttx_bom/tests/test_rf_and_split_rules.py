"""RF plant exclusion and the Grant / Non-Grant split rules learned from the Melcher-Dallas (DMI-R15) BOM."""
import json
from pathlib import Path

import openpyxl

from fttx_bom.engine import policies as pol
from fttx_bom.engine.network import GRANT, NONGRANT
from fttx_bom.engine.takeoff import Takeoff, count_blocks, route_footage
from fttx_bom.extract.model import Drawing, Insert, Polyline
from fttx_bom.inputs.detect import bom_sheet_name, classify_xlsx

CONV = json.loads((Path(__file__).resolve().parents[1] / "config" / "conventions.json").read_text())
NET = "N-R01"


class Cls:
    """Everything in N-R01, x >= 1000 is Non-Grant."""
    networks = {NET: None}
    foreign: dict = {}
    nongrant: list = []
    nearest_assigned: list = []
    tolerance = 0.0

    def network_of(self, p, what="", strict=False):
        return NET

    def resolve(self, p, strict=False):
        return NET, "inside", 0.0

    def foreign_of(self, p, strict=False):
        return None

    def area_of(self, p):
        return NONGRANT if p[0] >= 1000 else GRANT


def test_renamed_bom_sheet_is_found(tmp_path):
    # the approved DMI BOM renames "OLM SF-8M BOM" to "OLM DMI-R15 BOM"
    assert bom_sheet_name(["Cabinet OLT BOM", "OLM DMI-R15 BOM", "Jumper Calculator"]) == "OLM DMI-R15 BOM"
    assert bom_sheet_name(["Cabinet OLT BOM", "OLM SF-8M BOM"]) == "OLM SF-8M BOM"
    assert bom_sheet_name(["Cabinet OLT BOM", "Sheet1"]) is None
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OLM DMI-R15 BOM"
    ws.append([None, "Residental Count", None, None, None, None, None, 67, 142])
    wb.save(tmp_path / "done.xlsx")
    assert classify_xlsx(tmp_path / "done.xlsx") == "bom_completed"


def _vault_design():
    d = Drawing("t", "test")
    d.block_census = {"CX1-VAULT": {}}
    d.inserts = [Insert("v_fiber", "CX1-VAULT", "RTE_UGPOLES", (0, 0)),
                 Insert("s1", "MC_SPLICE.dwg", "Fiber Splice", (20, 0), attribs={"NAME": "N-01001"}),
                 Insert("v_rf", "CX1-VAULT", "RTE_UGPOLES", (500, 0)),
                 Insert("amp", "CX1_TRIPAM", "Fiber Building", (530, 0)),
                 Insert("v_pull", "CX1-VAULT", "RTE_UGPOLES", (2000, 0))]  # fiber pull box: no RF device near
    return d


def test_rf_vault_not_counted():
    tk = Takeoff([NET])
    count_blocks(_vault_design(), CONV, Cls(), tk, "vault")
    assert tk.get("vault", NET, GRANT) == 1 and tk.get("vault", NET, NONGRANT) == 1  # v_fiber + v_pull
    assert [h for _k, h, _p, _w in tk.extra["rf_structures"]] == ["v_rf"]


def test_rf_power_supply_alone_is_not_evidence():
    # the coax-powered OLM hub vault sits beside an RF power supply: still a fiber vault
    d = _vault_design()
    d.inserts = [i for i in d.inserts if i.handle != "amp"] + [Insert("ps", "CX1_NONSPS", "DES_POWER", (530, 0))]
    tk = Takeoff([NET])
    count_blocks(d, CONV, Cls(), tk, "vault")
    assert tk.total("vault", NET) == 3 and not tk.extra.get("rf_structures")


def _route_design(aerial_fiber: bool):
    d = Drawing("t", "test")
    d.inserts = [Insert("ug", "CX1-FTG-N2", "RTE_UGTRENCH", (10, 5), attribs={"FTG": "300'"}),
                 Insert("st", "CX1-FTG-N2", "RTE_AESTRAND", (10, 505), attribs={"FTG": "512'"}),
                 Insert("far", "CX1-FTG-N2", "RTE_UGTRENCH", (5000, 5000), attribs={"FTG": "2374'"})]
    d.polylines = [Polyline("c1", CONV["cable_layers"]["underground"][0], [(0, 30), (600, 30)])]
    if aerial_fiber:
        d.polylines.append(Polyline("c2", CONV["cable_layers"]["aerial"][0], [(0, 530), (600, 530)]))
    return d


def test_rf_strand_not_counted():
    tk = Takeoff([NET])
    route_footage(_route_design(aerial_fiber=False), CONV, Cls(), tk)
    assert tk.get("route_aerial_ft", NET, GRANT) == 0  # DMI-R15: RF strand, approved BOM 0
    assert any(k == "route_aerial_ft" for k, *_x in tk.extra["rf_structures"])
    tk = Takeoff([NET])
    route_footage(_route_design(aerial_fiber=True), CONV, Cls(), tk)
    assert tk.get("route_aerial_ft", NET, GRANT) == 512  # fiber lashed to the strand: counted (NMK transport)


def test_trench_without_fiber_counted_but_listed_and_policy_drops_it():
    tk = Takeoff([NET])
    route_footage(_route_design(aerial_fiber=False), CONV, Cls(), tk)
    assert tk.get("route_ug_ft", NET, NONGRANT) == 2374  # counted (Credit River counts such trench)
    assert [h for *_x, h, _p in tk.extra["trench_no_fiber"]] == ["far"]
    pol.compute_variants(tk)
    assert tk.get("route_ug_ft@fiber_bearing", NET, NONGRANT) == 0


def _passing_takeoff(g, ng):
    tk = Takeoff([NET])
    tk.add("passings", NET, GRANT, g, "EA", "")
    tk.add("passings", NET, NONGRANT, ng, "EA", "")
    tk.add("pon_ports", NET, GRANT, 0, "EA", "")
    tk.add("pon_ports", NET, NONGRANT, 0, "EA", "")
    return tk


def test_sfp_nongrant_first_rule():
    # DMI-R15 approved BOM: Non-Grant = ROUNDUP(155/64) = 3, Grant = ROUNDUP(222/64) - 3 = 1
    tk = _passing_takeoff(67, 155)
    pol.compute_variants(tk)
    pol.apply(tk, {"sfp": "total_minus_ng"})
    assert (tk.get("pon_ports", NET, GRANT), tk.get("pon_ports", NET, NONGRANT)) == (1, 3)
    tk = _passing_takeoff(17, 212)  # NMK-R02: total ROUNDUP(229/64) = 4, NG 4 -> Grant 0
    pol.compute_variants(tk)
    pol.apply(tk, {"sfp": "total_minus_ng"})
    assert (tk.get("pon_ports", NET, GRANT), tk.get("pon_ports", NET, NONGRANT)) == (0, 4)


def test_drop_column_options():
    tk = Takeoff([NET])
    for a, v in ((GRANT, 10194), (NONGRANT, 25923)):
        tk.add("drop_ft", NET, a, v, "FT", "")
        tk.add("drop_ft_bom", NET, a, v, "FT", "")  # engine: drops in their own column
    pol.compute_variants(tk)
    want = {"both": (10194, 25923), "nongrant_only": (0, 25923), "total_nongrant": (0, 36117)}
    for opt, cells in want.items():
        pol.apply(tk, {"drop_columns": opt})
        assert (tk.get("drop_ft_bom", NET, GRANT), tk.get("drop_ft_bom", NET, NONGRANT)) == cells, opt
    pol.apply(tk, {})
    assert tk.policy_used["drop_columns"] == "both"  # Design standard: Grant = total - Non-Grant


def test_engine_option_kept_when_default_changes():
    # regression: compute_variants copied the engine value into the *default* option, so the engine's own
    # option vanished once the default became a different option
    tk = Takeoff([NET])
    tk.add("max10_upgrades", NET, GRANT, 0, "EA", "need-based")
    tk.add("ped_max10", NET, NONGRANT, 9, "EA", "")
    tk.add("max10_upgrades", NET, NONGRANT, 0, "EA", "need-based")
    pol.compute_variants(tk)
    assert tk.get("max10_upgrades@need_based", NET, NONGRANT) == 0
    pol.apply(tk, {})
    assert tk.policy_used["max10_upgrade"] == "max10_nongrant" and tk.get("max10_upgrades", NET, NONGRANT) == 9

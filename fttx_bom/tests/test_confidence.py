"""Confidence rating of BOM cells and their highlighting in the workbook."""
import openpyxl

from fttx_bom.engine import policies as pol
from fttx_bom.engine.doctor import Issue
from fttx_bom.engine.network import GRANT, NONGRANT
from fttx_bom.engine.rules import Rule, load_rules
from fttx_bom.engine.takeoff import Takeoff
from fttx_bom.excel.confidence import LOW, REVIEW, assess

NET = "N-R01"


def _rule(key, value, status="VERIFIED"):
    return Rule(key, None, value, "EA", status, True, "", "")


def test_levels():
    tk = Takeoff([NET])
    for a in (GRANT, NONGRANT):
        tk.add("ped_max5", NET, a, 3, "EA", "")
        tk.add("pass_res", NET, a, 10, "EA", "")
        tk.add("route_ug_ft", NET, a, 100, "FT", "")
    rules = [_rule("CBP-MAX5DSM24", "ped_max5"), _rule("Residential Count", "pass_res"),
             _rule("UG Footage", "route_ug_ft", "INFERRED"), _rule("FE0-FOSC450D66NT0T3V", "fosc450d")]
    flags = assess(rules, tk, [], {}, [])
    assert ("CBP-MAX5DSM24", NET, GRANT) not in flags  # verified rule, complete inputs
    assert flags[("Residential Count", NET, GRANT)].level == LOW  # no address list
    assert flags[("UG Footage", NET, NONGRANT)].level == REVIEW
    f = flags[("FE0-FOSC450D66NT0T3V", NET, GRANT)]
    assert f.level == LOW and "splice reports" in f.reasons[0]  # plain-language reason


def test_issue_and_edge_effects():
    tk = Takeoff([NET])
    for a in (GRANT, NONGRANT):
        tk.add("ped_max5", NET, a, 3, "EA", "")
        tk.add("cable_024", NET, a, 500, "FT", "")
    rules = [_rule("CBP-MAX5DSM24", "ped_max5"), _rule("FFA-F902402G5B", "cable_024")]
    issues = [Issue("INFO", "Boundaries", "NEAR_GRANT_EDGE", NET, "CX1-MAX5 ABC is 3.0 ft from a Non-Grant edge (counted NG)", "", ""),
              Issue("ERROR", "Cable", "CABLE_TOTAL_MISMATCH", NET, "X TO Y FC024: FTG 10 + SLK 5 != TOTAL 20", "", "")]
    flags = assess(rules, tk, issues, {}, [])
    assert flags[("CBP-MAX5DSM24", NET, GRANT)].level == REVIEW
    assert flags[("FFA-F902402G5B", NET, NONGRANT)].level == LOW


def test_unsettled_convention_flagged():
    tk = Takeoff([NET])
    for a, v in ((GRANT, 10194), (NONGRANT, 25923)):
        tk.add("drop_ft", NET, a, v, "FT", "")
        tk.add("drop_ft_bom", NET, a, v if a == NONGRANT else 0, "FT", "")
    pol.compute_variants(tk)
    pol.apply(tk, {})
    flags = assess([_rule("Total Drop Footage", "drop_ft_bom")], tk, [], {}, [])
    f = flags[("Total Drop Footage", NET, GRANT)]
    assert f.level == REVIEW and "not settled" in f.reasons[0]


def test_workbook_highlight_and_review_sheet(tmp_path):
    from test_review_regressions import _mini_template

    from fttx_bom.excel.writer import write_bom

    cfg, _rules = load_rules()
    rule = Rule("CBP-MAX5DSM24", None, "ped_max5", "EA", "INFERRED", True, "", "")
    tk = Takeoff([NET])
    tk.add("ped_max5", NET, GRANT, 5, "EA", "")
    tk.add("ped_max5", NET, NONGRANT, 7, "EA", "")
    flags = assess([rule], tk, [], {}, [])
    res = write_bom(_mini_template(tmp_path / "t.xlsx", "G"), tmp_path / "o.xlsx", tk, [rule], cfg, {}, flags)
    wb = openpyxl.load_workbook(tmp_path / "o.xlsx")
    assert wb.sheetnames[-1] == "BOM Review" and res.added_sheets == ["BOM Review"]
    cell = wb["OLM SF-8M BOM"]["H6"]
    assert cell.value == 5 and cell.fill.fgColor.rgb.endswith("FFEB9C") and "REVIEW" in cell.comment.text
    review = list(wb["BOM Review"].iter_rows(min_row=5, values_only=True))
    assert {r[0] for r in review} == {"H6", "I6"} and all(r[6] == REVIEW for r in review)

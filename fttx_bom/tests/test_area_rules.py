"""One Grant / Non-Grant rule for every line: Non-Grant = inside the Non-Grant boundaries, Grant = total - Non-Grant;
a structure on the boundary (< 5 ft inside) is Grant, and so are the cable span feeding it and the closure in it."""
import json
from pathlib import Path

from fttx_bom.engine.geometry import Region
from fttx_bom.engine.network import GRANT, NONGRANT, Classifier
from fttx_bom.engine.takeoff import StructureAreas, Takeoff, _spans, passings, structure_area
from fttx_bom.extract.model import Drawing, Insert
from fttx_bom.inputs.address_list import AddressList

CONV = json.loads((Path(__file__).resolve().parents[1] / "config" / "conventions.json").read_text())
NET = "N-R01"
NG_SQUARE = [(100, -100), (300, -100), (300, 100), (100, 100)]  # Non-Grant polygon, x 100..300


def _cls():
    return Classifier({NET: Region("net", "0", [(-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000)])},
                      [Region("ng", "1", NG_SQUARE)], 0, None)


def test_structure_on_boundary_is_grant():
    cls = _cls()
    assert structure_area(cls, (103, 0)) == GRANT  # 3 ft inside the edge: on the boundary
    assert structure_area(cls, (120, 0)) == NONGRANT
    assert structure_area(cls, (50, 0)) == GRANT


def test_span_feeding_a_boundary_ped_follows_the_ped():
    cls = _cls()
    d = Drawing("t", "test")
    d.inserts = [Insert("p1", "CX1-MAX5", "RTE_UGPOLES", (103, 0)), Insert("p2", "CX1-MAX5", "RTE_UGPOLES", (200, 0))]
    feeds = StructureAreas(d, CONV, cls).area
    # the cable vertex at the ped sits 2 ft further in (105, 0): the span still feeds the boundary ped -> Grant
    path, breaks = [(0, 0), (105, 0), (198, 0)], {}
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            breaks.setdefault((2 + dx, 0 + dy), []).append((105, 0))
    spans = _spans(path, breaks, cls, feeds=feeds, end=(200, 0))
    assert [(round(L), a) for L, a in spans] == [(105, GRANT), (93, NONGRANT)]
    # without the structure rule the first span would be Non-Grant (its end vertex is inside the polygon)
    assert [a for _L, a in _spans(path, breaks, cls)] == [NONGRANT, NONGRANT]


def test_residential_nongrant_by_boundary_counted_once():
    cls = _cls()
    d = Drawing("t", "test")
    d.inserts = [
        Insert("a1", "FMRESADD2", "Address", (150, 0), attribs={"STREET_NUMBER": "1", "STREET_NAME": "MAIN ST"}),
        Insert("a1b", "FMRESADD2", "Address", (152, 0), attribs={"STREET_NUMBER": "1", "STREET_NAME": "MAIN ST"}),  # duplicate block
        Insert("a2", "FMRESADD2", "GRANTADDRESS", (160, 0), attribs={"STREET_NUMBER": "2", "STREET_NAME": "MAIN ST"}),  # layer says Grant
        Insert("a3", "FMRESADD2", "Address", (-500, 0), attribs={"STREET_NUMBER": "3", "STREET_NAME": "MAIN ST"}),  # layer says NG
        Insert("hc", "CX1-COUNT", "Address", (0, 0), attribs={"HC": "5"}),
    ]
    al = AddressList(NET, "x.xlsx")
    tk = Takeoff([NET])
    passings(d, CONV, cls, tk, {NET: al})  # empty address list: every block counts, from the drawing count blocks
    # Non-Grant = 2 distinct addresses inside the polygon (1 and 2 MAIN ST), Grant = 5 - 2
    assert (tk.get("pass_res", NET, GRANT), tk.get("pass_res", NET, NONGRANT)) == (3, 2)
    tk2 = Takeoff([NET])
    passings(d, dict(CONV, passings_area_rule="grant_layer"), cls, tk2, {NET: al})
    assert (tk2.get("pass_res", NET, GRANT), tk2.get("pass_res", NET, NONGRANT)) == (1, 4)

"""Fast unit tests (synthetic fixtures only)."""
import struct

import pytest

from fttx_bom.cli import project_from_filename
from fttx_bom.engine.geometry import Region, length_inside, point_in_polygon, polyline_length
from fttx_bom.engine.network import GRANT, NONGRANT, Classifier
from fttx_bom.engine.rules import Rule, evaluate
from fttx_bom.engine.takeoff import ServedIndex, Takeoff, _spans, addr_tokens, num, split_ratio
from fttx_bom.excel.writer import CONST_FORMULA
from fttx_bom.extract.proxy import BitReader, proxy_polylines
from fttx_bom.inputs.address_list import AddressList, ServedAddress
from fttx_bom.inputs.splice_reports import SpliceReport, network_from_splice_name

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


class BitWriter:
    def __init__(self):
        self.bits = []

    def put(self, value, n):
        self.bits += [(value >> (n - 1 - i)) & 1 for i in range(n)]

    def raw(self, b: bytes):
        for byte in b:
            self.put(byte, 8)

    def bytes(self):
        bits = self.bits + [0] * (-len(self.bits) % 8)
        return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


def make_proxy_lwpolyline(points):
    """Encode an R2000+ LWPOLYLINE body (flag 512 = closed) inside proxy graphics opcode 33."""
    w = BitWriter()
    w.put(0b00, 2)
    w.raw(struct.pack("<H", 512))  # BS flag via RS
    w.put(0b00, 2)
    w.raw(struct.pack("<I", len(points)))  # BL count via RL
    w.raw(struct.pack("<dd", *points[0]))
    for x, y in points[1:]:
        w.put(0b11, 2)
        w.raw(struct.pack("<d", x))  # DD full double
        w.put(0b11, 2)
        w.raw(struct.pack("<d", y))
    body = w.bytes()
    cmd_data = struct.pack("<I", len(body)) + body
    cmd = struct.pack("<II", 8 + len(cmd_data), 33) + cmd_data
    return struct.pack("<II", 8 + len(cmd), 1) + cmd


def test_proxy_lwpolyline_roundtrip():
    pts = [(1552360.25, 16206134.5), (1552460.25, 16206134.5), (1552460.25, 16206234.5)]
    polys = proxy_polylines(make_proxy_lwpolyline(pts))
    assert len(polys) == 1
    got, closed = polys[0]
    assert closed
    assert got == pts


def test_bitreader_codes():
    w = BitWriter()
    w.put(0b10, 2)  # BS -> 0
    w.put(0b11, 2)  # BS -> 256
    w.put(0b01, 2)
    w.put(7, 8)  # BS -> RC 7
    w.put(0b01, 2)  # BD -> 1.0
    w.put(0b00, 2)  # DD -> default
    r = BitReader(w.bytes())
    assert (r.bs(), r.bs(), r.bs(), r.bd(), r.dd(42.0)) == (0, 256, 7, 1.0, 42.0)


def test_geometry():
    assert point_in_polygon((50, 50), SQUARE)
    assert not point_in_polygon((150, 50), SQUARE)
    assert polyline_length([(0, 0), (3, 4)]) == 5
    # half of a 200 ft line inside the square
    assert length_inside([(-100, 50), (100, 50)], [Region("ng", "1", SQUARE)], step=1) == pytest.approx(100, abs=1)


def test_address_tokens_directionals_regression():
    # regression: '23955 N BEARD AVE' (address list) must match drawing block '23955' + 'BEARD'
    al = AddressList("NMK-R02", "x", served=[ServedAddress(1, 1, "23955 N BEARD AVE", "", "", "")])
    idx = ServedIndex(al)
    assert addr_tokens("23955 BEARD") in idx
    assert addr_tokens("23956 BEARD") not in idx


def test_address_tokens_unnumbered_and_commercial_regression():
    # regression (DMI-R15): unnumbered / vacant served locations and C- commercial prefixes
    al = AddressList("DMI-R15", "x", served=[ServedAddress(1, 1, a, "", "", "") for a in
                                             ("78TH AVE AVE", "VAC 708 RUTLEDGE ST", "C-9030 247TH ST E")])
    idx = ServedIndex(al)
    assert addr_tokens("78TH AVE") in idx
    assert addr_tokens("VAC 708 RUTLEDGE") in idx
    assert addr_tokens("C-9030 247TH") in idx


def test_split_ratio_sources():
    rep = SpliceReport("p", "DMI-15001G", "DMI-R15", "FOSC 450D", None, couplers=[(32, "FE0-F1PLC32")] * 7)
    assert split_ratio("DMI-R15", [rep], {})[0] == 32
    al = AddressList("X-R01", "x", coupler_ratios=[64, 64])
    assert split_ratio("X-R01", [], {"X-R01": al})[0] == 64
    assert split_ratio("X-R02", [], {})[0] is None


def test_network_from_splice_name():
    assert network_from_splice_name("NMK-02001G") == "NMK-R02"
    assert network_from_splice_name("DMI-15204G") == "DMI-R15"
    assert network_from_splice_name("NMK-R-23346 NATCHEZ AVE") is None


def test_num_parsing():
    assert num("2884'") == 2884
    assert num("25.00") == 25.0
    assert num("") is None


def test_constant_formula_detection():
    for f in ("=3+1", "=4", "=63586-9429", "=3+1+1"):
        assert CONST_FORMULA.match(f)
    for f in ("=J19", "=SUM(H19:H20)*2", "=IF(H18=0,1,0)"):
        assert not CONST_FORMULA.match(f)


def test_project_from_filename():
    assert project_from_filename("b04da51e-386106_Credit_River_MN_FTTH_Combined_DWG.dwg") == {"number": "386106", "name": "Credit River, MN"}
    assert project_from_filename("386021_MelcherDallas_BEAD_FTTH_DMI-R15_DWG.dwg") == {"number": "386021", "name": "Melcher Dallas"}


def test_spans_majority_area():
    cls = Classifier({}, [Region("ng", "1", [(50, -10), (200, -10), (200, 10), (50, 10)])], 0, "N")
    path = [(0, 0), (40, 0), (100, 0)]
    breaks = {}
    for p in [(40, 0)]:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                breaks.setdefault((int(p[0] // 50) + dx, int(p[1] // 50) + dy), []).append(p)
    spans = _spans(path, breaks, cls)
    # span 1: 0-40 ft entirely outside the Non-Grant polygon; span 2: 40-100 ft with 50 of 60 ft inside
    assert [(round(L), a) for L, a in spans] == [(40, GRANT), (60, NONGRANT)]


def test_rule_evaluation_never_silent_zero():
    tk = Takeoff(["N"])
    tk.add("olm", "N", GRANT, 1, "EA", "")
    tk.add("olm", "N", NONGRANT, 0, "EA", "")
    assert evaluate(Rule(None, "x", "3*olm", "EA", "VERIFIED", True, "", ""), tk, "N", GRANT) == (3, "")
    v, note = evaluate(Rule(None, "x", "missing_key", "EA", "VERIFIED", True, "", ""), tk, "N", GRANT)
    assert v is None and "not computed" in note
    v, note = evaluate(Rule(None, "x", "2*missing_key", "EA", "VERIFIED", True, "", ""), tk, "N", GRANT)
    assert v is None and "missing" in note


def test_template_formula_repair_and_area_columns():
    # regression: blank per-OLM template has I28 =SUM(I21:I22) while H28 =SUM(H19:H20)*2
    import openpyxl
    from fttx_bom.excel.writer import area_columns
    from openpyxl.formula.translate import Translator

    wb = openpyxl.Workbook()
    ws = wb.active
    for c, v in zip("BCDEFGHIJKL", ["Part Number", "", "", "", "", "Total Quantity", "Cabinet Name", "Cabinet Name", "Cabinet Name", "Cabinet Name", None]):
        ws[f"{c}5"] = v
    assert area_columns(ws, 5, 8) == ["H", "I", "J", "K"]
    assert Translator("=SUM(H19:H20)*2", origin="H28").translate_formula("I28") == "=SUM(I19:I20)*2"


def test_takeoff_subset_per_olm():
    tk = Takeoff(["A-R01", "A-R02"])
    tk.add("olm", "A-R01", GRANT, 1, "EA", "")
    tk.add("olm", "A-R02", GRANT, 1, "EA", "")
    tk.check("drops vs passings A-R02", False, "x", warn=True)
    sub = tk.subset(["A-R01"])
    assert sub.columns == [("A-R01", GRANT), ("A-R01", NONGRANT)]
    assert sub.total("olm") == 1 and not sub.checks

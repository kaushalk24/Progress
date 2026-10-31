"""Drawing cross-check tests and an optional integration test on a real reference pack.

Set FTTH_REFERENCE_PACK to a folder containing 'Splice Reports/' and 'Address List/' (and optionally
a .dwg) to run the integration test, e.g.:
    FTTH_REFERENCE_PACK=C:/packs/region_a python -m pytest tests
"""

import os
from pathlib import Path

import pytest

from ftth_addrlist.builder import Builder
from ftth_addrlist.compare import compare
from ftth_addrlist.config import load_config
from ftth_addrlist.drawing import address_coverage, crosscheck, read_drawing_inventory
from ftth_addrlist.network import Network
from ftth_addrlist.splice_reports import load_reports

from fixtures import CAB, HUB, OLM, build_network


def _build(folder):
    cfg = load_config()
    reps, _ = load_reports(sorted(folder.glob("*.xlsx")), cfg)
    return Builder(Network(reps, cfg), cfg).build(OLM), cfg


def test_dxf_crosscheck(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    res, cfg = _build(build_network(tmp_path / "r"))
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_text(HUB, dxfattribs={"insert": (0, 0)})
    msp.add_mtext(f"{CAB}\\PTST-00002")
    blk = doc.blocks.new("CLOSURE")
    blk.add_attdef("NAME", (0, 0))
    msp.add_blockref("CLOSURE", (5, 5)).add_auto_attribs({"NAME": "TST-00010"})
    adr = doc.blocks.new("ADDRESS_POINT")
    adr.add_attdef("STREET_NUMBER", (0, 0))
    adr.add_attdef("STREET_NAME", (0, 1))
    for n in (100, 200, 999):
        msp.add_blockref("ADDRESS_POINT", (n, 0)).add_auto_attribs({"STREET_NUMBER": str(n), "STREET_NAME": "MAIN ST"})
    path = tmp_path / "design.dxf"
    doc.saveas(path)
    inv, issues = read_drawing_inventory(path, cfg)
    assert inv["complete"] and {"TST-00001G", "TST-00002", "TST-00010"} <= inv["closures"]
    assert CAB in inv["cables"]
    rows, x_issues = crosscheck(res, inv)
    missing = {r["identifier"] for r in rows if r["found"] == "no"}
    assert "TST-00003" in missing          # break-point closure not drawn in this test drawing
    assert any(i.code == "DRAWING_COVERAGE" and i.severity == "WARNING" for i in x_issues)
    cov, cov_issues = address_coverage([res], inv)
    drawn_only = {r["identifier"] for r in cov if r["found"] == "drawing only"}
    listed_only = {r["identifier"] for r in cov if r["found"] == "list only"}
    assert drawn_only == {"999 MAIN ST"} and listed_only == {"300 MAIN ST", "400 MAIN ST"}
    assert cov_issues[0].severity == "WARNING"


def test_unsupported_and_missing_drawing(tmp_path):
    cfg = load_config()
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF")
    assert read_drawing_inventory(p, cfg)[0] is None
    inv, issues = read_drawing_inventory(tmp_path / "nope.dwg", cfg)
    assert inv is None and issues[0].code == "DRAWING_MISSING"


def test_bad_dwg_reported(tmp_path):
    p = tmp_path / "bad.dwg"
    p.write_bytes(b"AC1015" + b"\0" * 200)
    inv, issues = read_drawing_inventory(p, load_config())
    assert inv is None and issues[0].code == "DRAWING_UNREADABLE"


PACK = os.environ.get("FTTH_REFERENCE_PACK")


@pytest.mark.skipif(not PACK, reason="FTTH_REFERENCE_PACK not set")
def test_reference_pack():
    """Structural fields must match the completed lists exactly; every row must be present."""
    pack = Path(PACK)
    cfg = load_config()
    reps, _ = load_reports(sorted((pack / "Splice Reports").rglob("*.xlsx")), cfg)
    net = Network(reps, cfg)
    refs = sorted((pack / "Address List").glob("*.xlsx"))
    assert refs
    results = {o: Builder(net, cfg).build(o) for o in net.olms()}
    dwgs = list(pack.rglob("*.dwg"))
    if dwgs:   # Fiber Splice from the drawing: every row filled, agreement with the completed lists >= 99 %
        from ftth_addrlist.design import load_design
        from ftth_addrlist.drawing_splice import resolve_from_drawing
        inv, _ = read_drawing_inventory(dwgs[0], cfg)
        assert inv and inv["complete"] and len(inv["closures"]) > 100
        design, _ = load_design(dwgs[0], cfg)
        resolve_from_drawing(list(results.values()), net, design, cfg)
    agree = compared = 0
    for ref in refs:
        olm = next(o for o in net.olms() if o in ref.name)
        res = results[olm]
        c = compare(res, ref, cfg)
        assert c.matched == c.ref_rows == c.gen_rows and c.order_identical
        for f in ("pon_name", "pon_port", "fiber_no", "cable_name"):
            assert c.field_stats[f]["exact"] == c.field_stats[f]["compared"], (olm, f)
        assert c.field_stats["tap_name"]["normalised"] >= c.field_stats["tap_name"]["compared"] - 2, olm
        agree += c.field_stats["fiber_splice"]["normalised"]
        compared += c.field_stats["fiber_splice"]["compared"]
        if dwgs:
            assert not [r for r in res.rows if r.fields["fiber_splice"].status == "UNRESOLVED"], olm
    if dwgs:
        assert agree >= 0.99 * compared


def test_gui_config_picker():
    pytest.importorskip("tkinter")
    from ftth_addrlist.gui import DEFAULT_CONFIG_LABEL, config_description, regional_configs
    cfgs = regional_configs()
    assert cfgs[DEFAULT_CONFIG_LABEL] is None and "Desk study acceptance" in cfgs
    text = config_description(cfgs["Desk study acceptance"])
    assert "FS-DROP" in text and "FS-DRAWING" in text
    assert "nothing is accepted" in config_description(None)

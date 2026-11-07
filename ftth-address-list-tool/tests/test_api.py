"""The integration interface: api.generate (in memory) and the JSON file written next to each workbook carry
exactly the address list the workbook shows."""

import json

import openpyxl
import pytest

from ftth_addrlist.api import SCHEMA, SCHEMA_VERSION, generate, load_json
from ftth_addrlist.pipeline import InputError, run

from fixtures import OLM, build_network

FIELDS = ["pon_name", "pon_port", "fiber_no", "address", "tube_color", "fiber_color", "cable_name", "tap_name",
          "fiber_splice"]


@pytest.fixture
def region(tmp_path):
    reports = build_network(tmp_path / "reports")
    outs = run(reports, tmp_path / "out", prefix="API", log=lambda *a: None)
    return reports, outs[0]


def test_json_written_next_to_the_workbook_matches_it(region):
    _, oc = region
    assert oc.json is not None and oc.json.exists() and oc.json.stem == oc.workbook.stem
    data = load_json(oc.json)
    assert (data["schema"], data["schema_version"], data["olm"]) == (SCHEMA, SCHEMA_VERSION, OLM)
    assert [c["field"] for c in data["columns"]] == FIELDS
    ws = openpyxl.load_workbook(oc.workbook, read_only=True).worksheets[0]
    sheet = [list(r) for r in ws.iter_rows(min_row=2, values_only=True)]
    assert len(sheet) == len(data["rows"])
    for cells, row in zip(sheet, data["rows"]):
        assert [None if v is None else str(v) for v in cells[:len(FIELDS)]] == \
            [None if row[f] is None else str(row[f]) for f in FIELDS]
    assert data["counts"] == oc.counts and data["final"] == oc.final
    assert all(set(r["cells"]) == set(FIELDS) for r in data["rows"])


def test_generate_in_memory_equals_the_json_file(region):
    reports, oc = region
    on_disk = load_json(oc.json)
    in_memory = generate(reports)
    assert len(in_memory) == 1
    for d in (on_disk, in_memory[0]):
        d.pop("run_at")
    assert json.loads(json.dumps(in_memory[0], default=str)) == on_disk


def test_generate_reports_bad_inputs_clearly(tmp_path):
    with pytest.raises(InputError, match="not found"):
        generate(tmp_path / "missing")
    reports = build_network(tmp_path / "reports")
    with pytest.raises(InputError, match="Design drawing not found"):
        generate(reports, drawing=tmp_path / "none.dwg")


def test_load_json_rejects_other_files(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_json(p)

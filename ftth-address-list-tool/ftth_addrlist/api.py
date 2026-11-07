"""Stable interface for other programs (for example a callout generator).

Python:

    from ftth_addrlist.api import generate
    lists = generate("path/to/splice reports", drawing="path/to/region.dwg")
    for olm in lists:                       # one dict per OLM, the same content as the workbook
        for row in olm["rows"]:
            row["address"], row["tap_name"], row["fiber_splice"], row["status"]

Any language: every run also writes `<workbook name>.json` next to the workbook, with exactly this
structure. The structure is described in docs/INTEGRATION.md; `schema_version` changes only when a
field is removed or changes meaning (new fields may be added).

Nothing here changes how the address list is made: `generate` calls the same `pipeline.build` as the
window and the command line.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import __version__
from .builder import OlmResult
from .config import load_config

SCHEMA = "ftth-address-list"
SCHEMA_VERSION = 1


def olm_to_dict(res: OlmResult, cfg: dict, run_at: str | None = None) -> dict:
    """One OLM's address list as plain data (str / int / bool / None, lists, dicts)."""
    cols = cfg["template"]["columns"]
    fields = [c["field"] for c in cols]
    rows = []
    for n, r in enumerate(res.rows, 1):
        row = {"row": n, "kind": r.kind, "status": r.status, "section": r.cable, "cable_fiber": r.fiber}
        for f in fields:
            v = r.fields[f].value
            row[f] = v if v is None or isinstance(v, (int, float, bool)) else str(v)
        row["cells"] = {f: {"status": r.fields[f].status, "code": r.fields[f].code, "note": r.fields[f].note}
                        for f in fields}
        row["route"] = list(r.route)
        row["terminal_kind"] = (r.trace_end or {}).get("terminal_kind")
        rows.append(row)
    return {
        "schema": SCHEMA, "schema_version": SCHEMA_VERSION, "tool_version": __version__, "run_at": run_at,
        "olm": res.olm, "hub": res.hub, "final": res.is_final, "counts": dict(res.counts),
        "columns": [{"field": c["field"], "header": c["header"]} for c in cols],
        "sections": [{"cable": c, "segment": s, "fibers": k} for c, s, k in res.sections],
        "rows": rows,
        "issues": [{"severity": i.severity, "code": i.code, "message": i.message, "cable": i.cable,
                    "fiber": i.fiber, "source": i.source} for i in res.issues],
    }


def write_json(res: OlmResult, cfg: dict, path: Path, run_at: str | None = None) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(olm_to_dict(res, cfg, run_at), fh, indent=1, ensure_ascii=False)
    return path


def generate(reports: str | Path, *, drawing: str | Path | None = None, olms: list[str] | None = None,
             config: str | Path | None = None, overrides: str | Path | None = None, log=None) -> list[dict]:
    """Make the address list(s) in memory and return one dict per OLM (see olm_to_dict). Writes no files.
    Raises pipeline.InputError / config.ConfigError for unusable inputs, with a message for the user."""
    from .pipeline import build, check_inputs
    cfg = load_config(config)
    check_inputs(drawing=drawing, overrides=overrides)
    b = build(reports, olms, cfg, overrides, drawing, log or (lambda *_: None))
    return [olm_to_dict(b.results[o], cfg, b.run_at) for o in b.targets]


def load_json(path: str | Path) -> dict:
    """Read a JSON address list written by `run` (checks it is one)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: not an FTTH address-list JSON file")
    if int(data.get("schema_version", 0)) > SCHEMA_VERSION:
        raise ValueError(f"{path}: written by a newer tool (schema {data['schema_version']}); update this tool")
    return data

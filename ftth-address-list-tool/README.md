# FTTH Address List Generator

Generates OLM address-list workbooks (`PON NAME … Fiber Splice` layout) from the
**Splice Connections Reports** exported from the spatial system. Every cell is
traceable to the report rows it came from and carries a status:

| Status | Meaning | Cell colour |
|---|---|---|
| **CONFIRMED** | Read directly from, or traced through, explicit splice-report records | none |
| **PROVISIONAL** | Derived by a documented inference (e.g. the closure report that would show the tap splice was not supplied) – needs review | amber |
| **UNRESOLVED** | Cannot be determined from the inputs (missing or conflicting data) – value left blank | red |
| **APPROVED** | Supplied or accepted by a named person in the overrides file, or by an accepted rule policy | blue |

A workbook is named `…_FTTH_Address List.xlsx` only when every row is CONFIRMED or
APPROVED and there are no errors. Otherwise it is written as
`…_FTTH_Address List_DRAFT-REVIEW-REQUIRED.xlsx` and its *Run Info* sheet says
**DRAFT – NOT FOR ISSUE**. Existing files are never overwritten (a ` (2)` suffix is added).

## Quick start (Windows)

1. Install Python 3.11 or newer from python.org (tick *Add Python to PATH*).
2. Double-click **`FTTH Address List Tool.bat`**. On first use it installs `openpyxl`.
3. In the window:
   * **Splice reports folder** – the folder holding the region's splice reports
     (sub-folders per OLM are fine; all `.xlsx` files are read). Include the hub
     report for each OLM **and as many downstream closure reports as possible**.
   * **Output folder** – where results are written.
   * **File name prefix** – e.g. `123456_Example City ST`.
   * Optional: drawing (`.dxf` preferred, `.dwg` experimental), regional config,
     approved overrides CSV, completed workbooks to compare against.
   * **Scan** lists the OLMs found; leave *OLM* blank to generate all of them.
4. Click **Generate address list(s)**.

Command line (same options): `run_cli.bat run --reports "<folder>" --out "<folder>" --prefix "<prefix>"`
(see `python -m ftth_addrlist --help`).

## What is produced (per OLM)

| File | Content |
|---|---|
| `<prefix>_<OLM>_FTTH_Address List[_DRAFT-REVIEW-REQUIRED].xlsx` | Sheet `<OLM>`: the address list in template layout. Sheets *Row Status*, *Field Evidence* (value, status, rule code, derivation and source rows for every cell), *Exceptions* (with the action needed), *Reports to Request*, *Drawing Cross-check* (if a drawing was given), *Run Info* (verdict, counts, inputs with SHA-256). |
| `…_review_worklist.csv` | Every provisional/unresolved cell, pre-filled in overrides format. Fill in `action`, `value`, `approved_by`, `approved_on`, `reason` and use it as the overrides file. |
| `…_splice_reports_to_request.csv` | Closure reports that would confirm the provisional/unresolved rows, ranked by rows affected. |
| `…_exceptions.csv`, `…_run_manifest.json` | Exception list; machine-readable run record (inputs, hashes, counts, config). |
| `comparison_with_reference.xlsx` | Only when completed workbooks are supplied: field- and row-level comparison. |

## Review and approval workflow

1. Generate → open the DRAFT workbook; amber/red cells are listed in *Row Status*.
2. Preferred fix: obtain the closure reports listed in *Reports to Request* and rerun.
3. Otherwise decide in `…_review_worklist.csv`:
   * `ACCEPT` – keep the generated provisional value (`value` must equal it);
   * `SET` – replace it, or fill an UNRESOLVED cell (`expected_generated` records what you overrode, so the override
     is flagged **stale** if the source data changes later).
   `approved_by` and `approved_on` are mandatory. Save as e.g. `overrides.csv`.
4. Rerun with the overrides file. Decisions are keyed on OLM + cable name + fibre number,
   so they survive reruns and row re-ordering.
5. An engineering lead may accept a whole inference rule for a project in the config
   (`[approvals] accepted_rules = ["FS-CABLE-END"]`); such values show as APPROVED, never CONFIRMED.

## Configuration

`config/default_config.toml` holds the template mapping, colour codes, splitter and
PON conventions, usage-text rules and approval policy. Copy
`config/example_region.toml` for a region and set only what differs. Nothing in the
code is specific to the reference region.

## Batch

`python -m ftth_addrlist batch --jobs jobs.csv` with columns
`reports,out_dir,olm,config,overrides,prefix,reference,drawing` (paths relative to the CSV).

## Documentation

* [docs/FIELD_MAPPING.md](docs/FIELD_MAPPING.md) – every output column: meaning, source, rule, joins, validation, rule codes.
* [docs/INPUT_REQUIREMENTS.md](docs/INPUT_REQUIREMENTS.md) – input matrix, DWG/DXF workflow, **export checklist for a new region**.
* [docs/VALIDATION.md](docs/VALIDATION.md) – method and results against the completed reference pack, known limitations.

## Development

```
pip install -r requirements.txt pytest
python -m pytest tests                      # synthetic tests (no client data in the repo)
FTTH_REFERENCE_PACK=<pack folder> python -m pytest tests   # adds the reference-pack test
```

Dependencies: Python ≥ 3.11, `openpyxl`; `ezdxf` only for the DXF cross-check;
Tkinter (bundled with Python on Windows) for the window.

Layout: `ftth_addrlist/` – `splice_reports.py` (readers), `network.py` (connectivity
and fibre tracing), `builder.py` (rules), `overrides.py`, `workbook.py`, `compare.py`,
`drawing.py` + `dwg_container.py` (drawing inventory), `pipeline.py`, `cli.py`, `gui.py`.

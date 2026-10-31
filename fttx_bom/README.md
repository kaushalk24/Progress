# FTTx BOM Tool (`fttx_bom`)

Turns an FTTx design into a completed BOM on the approved Excel template. The inputs are the drawing, its address lists and its splice reports. The tool deep-checks the inputs and explains every number it writes.

```
DWG/DXF + address lists + splice reports (+ template, + optional approved BOM)
   -> FINAL_BOM.xlsx, BOM_AUDIT.xlsx, ISSUES.csv + ISSUES.scr (AutoCAD), BOM_DISCREPANCIES.xlsx (with an approved BOM)
```

## 1. Install (Windows, once)

1. Install **Python 3.11+** from python.org (tick *Add python.exe to PATH*).
2. Install **Node.js 20 LTS** from nodejs.org. It is needed to read DWG files directly; no AutoCAD licence is needed.
3. Optional: install **LibreOffice**, so the tool can recalculate and check every formula in the produced BOM.
4. Double-click `windows\setup.bat`.

On Linux or macOS:

```bash
pip install -r requirements.txt
```

```bash
cd tools && npm install --ignore-scripts && cd ..
```

## 2. Before you run: AutoCAD

Run **FXAUTO** (FX_DROPS.lsp) in the drawing and save. The drop-footage line is read from those drop lines. FXMISSING should show no gaps.

## 3. Use the app

Double-click `windows\run_app.bat`, or run:

```bash
python -m fttx_bom app
```

A browser page opens. Everything runs on your computer.

- **Run a job:** drop *everything* in one go: the DWG, address list(s), splice reports (files or zip), the blank BOM template and, optionally, an approved BOM. The tool identifies each file from its content. You get:
  - the BOM: one file per OLM when the template holds one OLM;
  - the audit;
  - the deep-check issue list;
  - an AutoCAD script that circles every located problem.
- **Batch:** a folder with one sub-folder per network. Each one gets its own outputs, plus a `BATCH_SUMMARY.xlsx`.
- **BOM guide:** how every BOM line is calculated, its status, and what reconciliation found.
- **Policies:** the conventions the drawing cannot settle (see section 6).

## 4. Command line

```bash
python -m fttx_bom auto "C:\Jobs\DMI-R15" --out "C:\Jobs\DMI-R15\out"
```

```bash
python -m fttx_bom batch "C:\Jobs" --out "C:\Jobs\out" --template "C:\Templates\FTTH_BOM.xlsx"
```

```bash
python -m fttx_bom run --dwg D.dwg --address-list "Address List" --splice-reports "Splice Reports" --template T.xlsx --out out
```

Useful options are `--reference approved.xlsx`, `--learn`, `--project-name`, `--project-number`, `--system "Capital West"` and `--no-recalc`. The exit code is 0 when the workbook verification passed.

## 5. Deep check: test and fix your own networks

Every run lists every problem. Each one has:

- a **severity**: ERROR (a BOM quantity is wrong until fixed), WARN (verify) or INFO;
- the **BOM lines it affects**;
- **how to fix it**: usually in AutoCAD (FXAUTO, FXMISSING, a label, a boundary) or in the address list;
- **drawing coordinates**, when it has a location.

In AutoCAD, type `SCRIPT` and pick `<job>_ISSUES.scr`. Each located issue is circled on layer BOM_CHECK_ERROR, _WARN or _INFO. Fix the drawing, save, and run the job again until there are no errors.

What it checks:
- drawing reader status;
- missing layers or blocks;
- blocks on design layers that are not mapped to any BOM line (possible missing materials);
- OLM boundaries, tiny or missing Non-Grant polygons, and objects within 15 ft of a Grant edge;
- duplicate address blocks, served addresses with no address block, grant addresses that are not served, and duplicate PON ports;
- cable labels: FTG + SLK = TOTAL, REQ + SPARE = TTL, REQ above the cable size, duplicates, labels against the splice reports, unlabelled cables, and drawn route length against the label;
- drops: missing, count against passings, served addresses without a drop, drops not starting at a ped, and very long drops;
- splice reports: unknown enclosure types, reports with no splice point in the drawing, and the second report layout;
- splitter design against passings and PONs;
- template formulas that differ between columns (repaired automatically);
- workbook verification;
- which policies change the totals.

## 6. Policies: accurate results without waiting for an SME

Some conventions can't be read from the drawing, so the tool computes **every option** on every run:

| Policy | Options |
|---|---|
| SFP | Jumper Calculator ÷ 2, split ratio, or designed PONs |
| Splitter Grant split | Grant first, or per column |
| Tray packages | pooled, per location, or fully pooled |
| MAX10 upgrade | need-based, all MAX10, or Non-Grant MAX10 |
| Drop columns | Non-Grant only, or both columns |
| Route footage | route labels (CalcFTG), or cable totals |
| Cable split | by span, or by length |
| OLM column | Grant if any grant passings, or by location |

The audit's *Policies* sheet shows every option's numbers side by side.

When you include an **approved BOM**, every option is scored against it cell by cell. With *Learn* (`--learn`), the best options are saved to `config/policies.json` and used for every new BOM. Each approved BOM you feed in adds evidence, so the tool keeps following your company's actual practice.

The current defaults are the SME walkthrough rules and your AutoCAD routines (FX_DROPS, CalcFTG). On the Credit River BOM, the default option scores at least as well as every alternative on every policy.

## 7. Outputs

| File | Content |
|---|---|
| `*_FINAL_BOM.xlsx` | Template with quantities in the Grant / Non-Grant columns. Formulas, part numbers, formatting, comments and links are kept; inconsistent template formulas are repaired and logged. |
| `*_BOM_AUDIT.xlsx` | Summary and coverage, Deep Check, every BOM line with its rule and status, Policies (all options), the full takeoff with CAD handles as evidence, cables, splice enclosures, checks, network assignment, and CAD census. |
| `*_ISSUES.csv` / `*_ISSUES.scr` | Issue list and AutoCAD circle script. |
| `*_BOM_DISCREPANCIES.xlsx` | Only with an approved BOM: differences per cell and per network, investigated causes, and policy calibration. |

Line statuses:
- **VERIFIED:** reproduces the approved BOM from independent sources.
- **VERIFIED_TOTAL:** network totals are verified; the Grant/Non-Grant split comes from the boundaries.
- **INFERRED:** a defensible rule.
- **NOT_DETECTED / UNRESOLVED:** left blank and flagged.

## 8. Configuration

| File | Purpose |
|---|---|
| `config/conventions.json` | Layer and block names, and blocks to ignore. |
| `config/bom_rules.json` | One rule per BOM line. |
| `config/policies.json` | Selected / learned policy options. |
| `config/investigations.json` | Documented reference differences. |

## 9. Tests

```bash
python -m pytest -q -m "not slow"
```

```bash
FTTX_TEST_DATA=/path/to/project/files python -m pytest -q
```

See `BOM_RULES.md`, `SME_MEETING_NOTES.md`, `PROGRESS_AND_ISSUES.md` and `CHANGELOG.md`.

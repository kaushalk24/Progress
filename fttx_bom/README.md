# FTTx BOM automation (`fttx_bom`)

Turns an FTTx design drawing plus its address list and splice reports into a
completed BOM on the approved Excel template, with an audit trail for every
quantity.

```
DWG (or DXF) + Address List + Splice Reports + BOM template
        -> FINAL_BOM.xlsx + BOM_AUDIT.xlsx (+ BOM_DISCREPANCIES.xlsx when a reference BOM is given)
```

## Install

Python 3.11+ and Node.js 20+.

```bash
pip install -r requirements.txt
```

```bash
cd tools && npm install --ignore-scripts && cd ..
```

`tools/` holds the DWG reader: LibreDWG compiled to WebAssembly
(`@mlightcad/libredwg-web`, pinned to 0.8.0). It reads AutoCAD 2018 (AC1032)
DWGs directly; no AutoCAD licence is needed. A DXF exported from AutoCAD
(`DXFOUT`) can be supplied instead and is read with `ezdxf`.

LibreOffice (`soffice`) is optional but recommended: it is used to recalculate
the workbook formulas and verify the totals after generation.

## Run

```bash
python -m fttx_bom \
  --dwg "386021_MelcherDallas_BEAD_FTTH_DMI-R15_DWG.dwg" \
  --address-list "386021_MelcherDallas_BEAD_FTTH_DMI-R15_Address List.xlsx" \
  --splice-reports "Splice Reports/" \
  --template "BOM_template.xlsx" \
  --project-name "Melcher-Dallas, IA" \
  --out out/DMI
```

Reconcile against a completed BOM (as done for Credit River NMK-R02..R05):

```bash
python -m fttx_bom --dwg 386106_Credit_River_MN_FTTH_Combined_DWG.dwg \
  --address-list "Address List/" --splice-reports "Splice Reports/" \
  --template "386106_Credit River MN_FTTH_Combined_BOM.xlsx" \
  --reference "386106_Credit River MN_FTTH_Combined_BOM.xlsx" \
  --system "Capital West" --out out/NMK
```

Before running: in AutoCAD, run **FXAUTO** (FX_DROPS.lsp) and save, so drop lines exist for the drop-footage row. If the template has fewer area columns than the job needs (the blank template holds one OLM), the tool writes one BOM per OLM.

Networks come from the address-list sheet names (`NMK-R02` ...) unless
`--networks` is given. The template holds up to 4 networks (8 Grant/Non-Grant
columns). Exit code 0 means every workbook verification check passed.

## Outputs

| File | Content |
|---|---|
| `<proj>_<networks>_FINAL_BOM.xlsx` | The template with quantities filled in the Grant / Non-Grant columns, headers, Jumper Calculator and Transport BOM inputs. Formulas, part numbers, formatting, comments and links are kept. |
| `<proj>_<networks>_BOM_AUDIT.xlsx` | Summary and coverage; every BOM line with its rule, status and per-column value; the full takeoff with CAD handles as evidence; per-cable routing and Grant split; splice enclosures; all checks; objects outside network boundaries; CAD entity census. |
| `<proj>_<networks>_BOM_DISCREPANCIES.xlsx` | Only with `--reference`: per cell and per network differences, with the investigated cause. |

Line statuses: **VERIFIED** reproduces the reference from independent
sources. **VERIFIED_TOTAL** means network totals are verified but the
Grant/Non-Grant split is inferred. **INFERRED** is a defensible rule that hasn't
been proven against an approved BOM. **UNRESOLVED** and **NOT_DETECTED** lines
are left blank for the engineer. **SUGGESTED** values appear in the audit only.

## Layout

```
fttx_bom/extract   DWG/DXF backends -> normalized drawing model; proxy-graphics decoder
fttx_bom/inputs    address list and splice report readers
fttx_bom/engine    network / Grant classification, takeoff, rule evaluation
fttx_bom/excel     template writer, verification (LibreOffice recalc), audit + discrepancy reports
config/            conventions.json (layer/block names), bom_rules.json (rule catalogue),
                   investigations.json (documented reference differences)
tests/             unit tests + integration tests (set FTTX_TEST_DATA, see tests/test_integration.py)
```

The CAD naming lives in `config/conventions.json` and the BOM row rules live in
`config/bom_rules.json`. New rules or symbols are added there, not in code.

## Tests

```bash
python -m pytest -q -m "not slow"
```

```bash
FTTX_TEST_DATA=/path/to/project/files python -m pytest -q
```

See `BOM_RULES.md`, `PROGRESS_AND_ISSUES.md` and `CHANGELOG.md`.

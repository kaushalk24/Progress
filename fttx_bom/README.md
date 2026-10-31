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

| Page | What it does |
|---|---|
| **New BOM** | Runs in three steps. **Inputs:** upload everything at once, or give folders; the drawing, address lists, splice reports and blank template are recognised by content. **Generate:** shows a status. **Results:** KPIs and tabs for *BOM preview*, *Cells to check*, *Design check*, *Excluded plant* and *Downloads*. |
| **Batch** | A folder with one sub-folder per network. Each gets its own outputs, plus `BATCH_SUMMARY.xlsx`. |
| **Design standards** | How every BOM line is derived. |
| **Settings** | Conventions the drawing cannot settle (section 6). |

### Confidence in the BOM

Every quantity in the generated BOM is rated:
- **Red (low confidence):** do not order without checking.
- **Amber (review):** check before ordering.

Each flagged cell has a comment explaining why, and the *BOM Review* sheet at the end of the workbook lists them all. Typical reasons are a missing address list or splice reports, no drop lines, an inferred rule, an unsettled convention, or a design warning on that line.

A warning only marks the cells whose number it can change:
- A cable warning marks the row of the fiber count it names, in its network.
- A cable whose route is not traced is marked only when its label and two ends are not all in the same area.
- An address on a layer that disagrees with the Non-Grant boundary marks the residential count. It marks splitters and SFP only where moving the address would change them.
- Unmapped symbols mark the rows written as 0 (GOAT peds, peds with tap) only when they sit on the pedestal layer.

Repeated reasons are shown once, with a count.

### Drawings with other plant

A drawing can also hold existing HFC plant or a fiber network designed by others. Only this design is counted: MAX5/MAX10 pedestals with bulkheads. Everything else is left out and listed with its reason on the audit's *Excluded* sheet and the app's *Excluded plant* tab.

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

### Running one OLM from a combined drawing

Give the tool only that OLM's address list (or `--networks NMK-R02`). The other networks' boundaries are recognised and their objects are excluded. Inter-network cables go to their A-end network, and the transport corridor goes only to the network fed by the OTN cable. The result is identical to the combined run.

### Re-running into the same folder

Outputs carry a marker. Files named `*_FINAL_BOM.xlsx` / `*_BOM_AUDIT.xlsx` and the output folder are never read back as inputs, so a rerun cannot use its own BOM as the "approved BOM".

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
- splitter design against passings and PONs, and a second split ratio in one network;
- ped size against the cable (a MAX5 at a mid-span splice on a cable above 48F) and closure capacity (trays per FOSC 450);
- cables that join two networks (booked to their A-end network);
- RF (coax) support structures left out (RF vaults, strand without fiber), trench without fiber, and served addresses whose layer disagrees with the Non-Grant boundary;
- boundaries: a job network with no boundary (its BOM is left blank), other networks in the same drawing (excluded), and boundary fallbacks;
- template formulas that differ between columns (repaired automatically);
- workbook verification;
- which policies change the totals.

## 6. Settings: conventions the drawing cannot settle

Some conventions can't be read from the drawing, so the tool computes **every option** on every run:

| Policy | Options |
|---|---|
| SFP | per column, Jumper Calculator splitters ÷ 2 rounded up (standard); network total − Non-Grant; split ratio; or designed PONs |
| Splitter Grant split | Grant first, or per column |
| Tray packages | pooled, per location, or fully pooled |
| MAX10 upgrade | template formula, one kit per Non-Grant MAX10 (default); need-based; or all MAX10 |
| Drop columns | both, Grant = total − Non-Grant (default); Non-Grant only; or all drops in Non-Grant |
| Route footage | route labels, as CalcFTG (default); cable totals; or fiber-bearing trench only |
| Cable split | span by span, each in the area of the ped it feeds (standard); span majority; or length inside the polygons |
| Ground wire kits | hand count, highlighted with the drawing's count: template-note criteria, G suffix only, or not ordered |
| OLM column | Grant if any grant passings, or by location |

The audit's *Policies* sheet shows every option's numbers side by side.

When you include an **approved BOM**, every option is scored against it cell by cell. With *Learn* (`--learn`), the best options are saved to `config/policies.json` and used for every new BOM. Each approved BOM you feed in adds evidence, so the tool keeps following your company's actual practice.

The current defaults are the design standards and your AutoCAD routines (FX_DROPS, CalcFTG). On the Credit River BOM, the default option scores at least as well as every alternative on every policy.

## 7. Outputs

| File | Content |
|---|---|
| `*_FINAL_BOM.xlsx` | Template with quantities in the Grant / Non-Grant columns. Formulas, part numbers, formatting, comments and links are kept; inconsistent template formulas are repaired and logged. Cells to check are coloured red / amber with a comment and listed on the *BOM Review* sheet. |
| `*_BOM_AUDIT.xlsx` | Summary and coverage, Deep Check, Review (flagged cells), Excluded (plant not in this design), every BOM line with its rule and status, Policies (all options), the full takeoff with CAD handles as evidence, cables, splice enclosures, checks, network assignment, and CAD census. |
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

See `DESIGN_STANDARDS.md` (the standard for every BOM line), `UI_DESIGN.md` (interface), `BOM_RULES.md` (rules and DWG→BOM chains), `FORENSIC_FINDINGS.md` (line-by-line reconstruction of the approved BOMs), `RESEARCH.md` (sources), `DESIGN_STANDARDS.md`, `PROGRESS_AND_ISSUES.md`, `CHANGELOG.md` and `RESEARCH_RECOVERY.md` (work checkpoint).

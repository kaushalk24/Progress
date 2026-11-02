# Changelog

## 0.8.0 - one Grant / Non-Grant rule, Windows application, interface polish

### One Grant / Non-Grant rule for every line
Non-Grant = inside the Non-Grant boundaries; Grant = total − Non-Grant.

- **Residential passings and drops** now follow the boundary, like the commercial, MDU, ped, vault and cable lines already did. They used to follow the GRANTADDRESS layer.
  - Both manual BOMs follow the layer. Where the layer and the boundary disagree, the layer booked a home Non-Grant while the peds, cable and drop serving it were Grant.
  - NMK has 25 such served addresses, 150–4,600 ft outside every Non-Grant polygon; DMI has 1 (2140 60TH).
  - The disagreements stay in the design check (ADDRESS_LAYER_VS_BOUNDARY) and the residential cell is marked for review with the layer-based number.
  - `passings_area_rule: "grant_layer"` in conventions.json restores the old count.
- **Each address is counted once.** Duplicate address blocks no longer inflate a count.
- **Structures on the boundary.** A structure less than 5 ft inside the Non-Grant edge counts as Grant. This now also holds for:
  - the cable span that feeds it;
  - the closure in it;
  - its ground and upgrade kits;
  - the near-edge design check, whose "counted ..." text used to ignore the rule.
- **Drop footage:** Grant drops go in the Grant column (confirmed). Those cells are no longer marked for review.

### Design check
- **ADDRESS_SERVED_TWICE:** the same address on two PON ports. NMK-R03 has two.
- **CABLE_SPAN_CROSSES_BOUNDARY:** a span that runs 300 ft or more through the other area than the ped it feeds, for example 1,600 ft at DMF-R04.

### Windows application
- `FTTx BOM Tool.exe` opens the application in its own window (Edge WebView2). If the window can't be created, it opens the default browser.
- `fttx-bom.exe` is the command line, plus `--selftest` and `--version`.
- Node.js and the DWG reader are bundled, so nothing else needs to be installed. LibreOffice is optional and found in its standard folder.
- Settings live in `%APPDATA%\FTTx BOM Tool` and jobs in `Documents\FTTx BOM Jobs`.
- **Build:** GitHub Actions on Windows runs the tests, builds with PyInstaller, runs the packaged self-test, and produces a per-user installer (Inno Setup, no administrator rights) and a portable zip. See `packaging/`.

### Interface
- **BOM preview:**
  - section, unit and total columns;
  - flagged cells coloured exactly as in the workbook;
  - thousands separators;
  - "Lines with a quantity / Cells to check / All lines";
  - a search box.
- **Network summary:** passings, peds, vaults, cable, route and drops as Grant / Non-Grant / Total.
- **Project name and number** come from the drawing's file name in folder mode too, and "MelcherDallas" becomes "Melcher Dallas".
- **Theme:** neutral blue.
- **Other:** an "Open output folder" button, and severity counts on the design-check filter.

### Fixes
- **Windows text encoding.** Every text file is read and written as UTF-8. Before, a drawing with a non-ASCII character (°, ½ ...) in its text could fail or come out garbled on Windows.
- **Flagged cells** keep the template's typeface and size.
- **`jinja2`** is listed in requirements.txt. The app falls back to an uncoloured table without it.

## 0.7.1 - targeted confidence

- **Highlighted cells are now only those whose number a finding can change.**
  - Cable warnings mark the row of the fiber count they name, in the cable's own network. Before, they marked every cable row of every network.
  - A duplicate cable label with identical values no longer marks anything, because it is counted once.
  - A cable whose route is not traced is marked only when its label and its two ends are not all in the same area.
  - An address whose layer disagrees with the Non-Grant boundary marks the residential count. It marks splitters and SFP only when moving the address would change them.
  - Unmapped symbols mark the 0-written pedestal rows only when they sit on the pedestal layer (an aerial symbol is not a pedestal).
  - Trench without fiber marks the UG and mileage rows, not aerial.
  - A closure over tray capacity marks only that closure's type (e.g. 450D and D trays), in its own area column.
  - Repeated reasons (one per address or per ped) are shown once, with a count.
- **App: the BOM preview tab paired every line with every description.** It now shows one row per written line, in template order, with its own description and values. The table is built in `fttx_bom/views.py` and covered by a test.
- **The pole-mount OLM enclosure** uses the same OLM-location test as the ground-mount lines and is rated the same (VERIFIED, design standard: pole or ground mount follows the OLM location).
- **The route footage and splice-tray rows follow the design standard** (CalcFTG route labels; trays ROUNDUP(splices / 24 or / 48), packages of 2) and are rated VERIFIED. The route-footage convention is no longer listed as unsettled. Trench with no fiber nearby is still marked for review.

## 0.7.0 - design scope, confidence highlighting, new interface

- **Drawings with other plant (DMF-R04).** Only this design is counted: MAX5/MAX10 pedestals with bulkheads.
  - **Existing HFC plant is left out:** taps, amplifiers, power supplies, RF pedestals, coax trench and strand, and their vaults.
  - **Fiber designed by others is left out:**
    - splices housed at MST terminals;
    - cables ending there or at an HFC node;
    - structures and trench on their routes;
    - count blocks at their terminals.

    Every excluded object is listed on the audit's *Excluded* sheet and on the app's *Excluded plant* tab.
  - **Without an address list,** passings come only from count blocks and addresses at this design's pedestals.
- **SpatialNet Non-Grant polygons stored as custom objects** (SNMPOLYGON) were silently missing from the drawing data. They are now recovered from their entity graphics. On DMF-R04, all 8 polygons are recovered, 7 of them labelled. The drawing cache is invalidated when the reader changes.
- **The network name comes from the drawing boundary** when no address list is supplied.
- **Confidence highlighting in the BOM.** Every quantity cell is rated low confidence (red) or review (amber), with the reason in a cell comment. A *BOM Review* sheet lists them all, and the audit and the app show the same list.
- **New interface:**
  - *New BOM* is a three-step page: inputs with detected files, generate with status, then results with KPIs and tabs (BOM preview, cells to check, design check, excluded plant, downloads).
  - The other pages are *Batch*, *Design standards* and *Settings*.
  - The plan is in UI_DESIGN.md.
- **Design-standard alignment:**
  - **SFP** is per column, ROUNDUP(Jumper Calculator splitters required / 2). On the Credit River BOM this gives 1/4/1/4/1/3/2/2.
  - **Cable split:** each span belongs to the ped or splice it feeds. NMK absolute cable error falls from 26,142 to 19,366 ft against the approved BOM.
  - **Boundaries:** pedestals and vaults on the Non-Grant boundary count as Grant.
  - **Fixed zeros:** GOAT and ped-with-tap rows are 0, because MAX peds use bulkheads.
  - **Ground wire kit** is a highlighted hand-count cell showing the drawing's count.
- **RF trench** (trench along coax with no fiber of this design) is no longer counted as route footage. NMK R04 UG goes down 684 ft.
- **Professional wording** throughout. DESIGN_STANDARDS.md documents every BOM line.
- **Tests:** 93 (92 without the slow end-to-end run). New: confidence, design scope (DMF-R04) and app pages.

## 0.6.0 - Melcher-Dallas approved BOM: Grant/Non-Grant standard, RF plant left out

Reconciled against the manual DMI-R15 BOM (see FORENSIC_FINDINGS.md "Melcher-Dallas"): 72 → 75 of 90 cells, 34 → 38 of 45 totals.

- **RF (coax) support structures are not calculated (design standard):**
  - vaults/L-boxes at an RF device with no fiber splice nearby are left out (DMI: 1 vault, now 8 = approved);
  - aerial strand with no aerial fiber cable is left out (DMI: 512 ft, now 0 = approved);
  - RF devices are never reported as unmapped materials.
- **Grant/Non-Grant standard** (Non-Grant inside the boundaries, Grant = total − Non-Grant):
  - SFP Non-Grant = ROUNDUP(NG/64), Grant = ROUNDUP(total/64) − Non-Grant. This is the new default; it reproduces DMI exactly and gives NMK 15 SFP for 15 designed PONs (the per-column option gave 18).
  - Drops: the new default is "both" (Grant = total − Non-Grant), with new option `total_nongrant` (the DMI BOM's convention). **Please confirm.**
- **MAX10 +4 kits:** the default is now the blank-template formula, one kit per Non-Grant MAX10 (reproduces DMI 0 / 9).
- **Ground wire kits** are no longer written: both approved BOMs leave the line blank. The audit keeps the template-note count.
- **Renamed BOM sheets:** approved BOMs and templates with a renamed OLM sheet ("OLM DMI-R15 BOM") are now read.
- **New deep checks:**
  - ADDRESS_LAYER_VS_BOUNDARY (WARN): a served address whose GRANTADDRESS layer disagrees with the Non-Grant polygons; NMK 25, DMI 2;
  - TRENCH_NO_FIBER (INFO, one per network);
  - RF_EXCLUDED (INFO).
- **Policy fix:** the engine's own option survives when a policy default changes (regression test).
- **Manual-BOM findings documented** (FORENSIC_FINDINGS D1–D14):
  - FC024 is double-counted (+6,467 ft, a duplicated drawing label);
  - row 6 has footage typed into the mileage row;
  - the bonding jumper and ped bonding kit inherit the template's inconsistent column formulas.
- **Credit River effect:** 8 cells now follow the design standard and the DMI convention instead of the Credit River practice (SFP Grant 3, MAX10 +4 3, Grant drops 2).
- **Tests:** 88 (87 without the slow end-to-end test).

## 0.5.0 - forensic review, independent code review, research-backed rules

### New rules from the forensic analysis (see FORENSIC_FINDINGS.md and BOM_RULES.md)
- **Ground wire kits (FE0-07264810)** are now written. The rule follows the blank template's note: one kit per splice location that meets any of these, counted once:
  - the splice name ends in G;
  - it is the first splice on each cable's route out of the OLM hub;
  - the name ends in 0;
  - it is an end of line.

  NMK gives 321 kits, DMI 126. New policy `ground_kits` (template_note / g_suffix / not_ordered). The Credit River BOM, made on the older template, left this line blank.
- **D basket (FE0-R89279) = 0:** the FOSC450-D6-6-NT-0-T3V closure ships with its tall basket. This comes from the CommScope ordering guide, and the approved BOM also orders 0.
- **Deep-check design rules:**
  - MAX5_ON_LARGE_CABLE (WARN): in both approved designs no MAX5 houses a splice (mid-span, branch or end) on a cable above 48F. Splices are tied to their nearest housing, and FOSC closure splices are excluded;
  - MAX10_SMALL_CABLE (INFO);
  - CLOSURE_OVER_CAPACITY (WARN: more trays than a FOSC 450 holds with its basket);
  - CABLE_CROSS_NETWORK (INFO).
- Policy calibration no longer counts a row that the approved BOM never filled in as evidence of 0.

### Fixed: findings of the independent code review (each has a regression test)
- **BLOCKER: one OLM run from a combined drawing.**
  - Before: it booked neighbouring OLMs' peds and vaults (within 150 ft), the whole transport corridor (5,279 ft aerial, about 7,000 ft UG) and inter-network cables to that OLM.
  - Now: other networks' boundaries are recognised and excluded, and a cable belongs to its A-end network in every kind of run.
  - Single-OLM runs now equal the combined run on every cell.
- **BLOCKER: boundary label not recognised.** A single-network job counted the whole drawing (MAX10 60 -> 260) with no error. Now:
  - the whole-drawing fallback is used only when the drawing has no boundary polygons (WARN);
  - otherwise the result is an ERROR, and that network's BOM is left blank instead of filled with false zeros;
  - the label regex is configurable.
- KeyError crash when the network fed by the transport corridor has no boundary.
- **Address list:** columns are now matched by name (case and order no longer matter). Sheets that are not address lists are skipped. An empty list falls back to the drawing counts instead of writing 0 or negative passings.
- **Mixed 1x32 / 1x64 designs:** the second ratio's designed splitters are written (they were 0) and a WARN is raised.
- **Enclosure types:** spellings such as "FOSC-450B", "450D" and "FOSC450-D" are recognised by one shared rule. Unknown types are flagged; SPLICE CASE is a known non-closure.
- **Rerun into the output folder:**
  - The tool's own FINAL_BOM was taken as the approved BOM, and with `--learn` it learned from itself.
  - The output folder and generated files are now skipped, and generated workbooks carry a marker.
- **One-OLM-per-BOM:** a 2-OLM job on the blank per-OLM template made one BOM and dropped the second OLM's Transport BOM. Capacity is now the smallest of the main, Transport and Jumper sheets.
- **Area columns** are located from the "Total Quantity" header. A shifted template no longer has its totals overwritten.
- **Computed zeros where nothing was computed:**
  - FOSC lines are left blank without splice reports;
  - a block missing from the drawing's definitions (a renamed symbol) gives a blank line and an ERROR, not 0.
- **Rule expressions** are evaluated by a restricted parser (no `eval`). A negative result is left blank.
- **Zip extraction:** size, entry and compression-ratio limits; two zips with the same name no longer merge.
- **LibreOffice:** with a relative `--out`, the recalculation hung for up to 15 minutes. The profile path is now absolute.
- **Splice reports:** a text number ("1,234", "48 ct") no longer aborts the job, and an unreadable report is skipped with an ERROR.
- The deep check no longer adds stray rows to the audit's Network Assignment sheet.
- Grant and Non-Grant cable cells now add up exactly to the rounded network total.
- Robustness: policy variants no longer crash on a cable size that has no base quantity.

### Research (RESEARCH.md)
- The FOSC 450 ordering guide confirms 2 trays per kit, 24 splices per B tray and 48 per D tray, and the tray limits per closure.
- LibreDWG and ezdxf limits are documented.
- No public source prescribes slack, the BEAD split or the ped grounding rules, so the tool keeps reading them from the design and the customer template.

### Tests
75 tests (74 run without `slow`). New files: `tests/test_forensic_rules.py` and `tests/test_review_regressions.py`.

## 0.4.0 - self-service tool: app, auto-detect, batch, deep check, learned policies
- **App** (`python -m fttx_bom app` / `windows\run_app.bat`): a local browser UI to upload or point at files, run, see the issue table and download all outputs. Also batch runs, a BOM guide (how every line is calculated) and a policy editor.
- **Auto-detection** (`auto` command): classifies DWG/DXF, address lists, both splice-report layouts, blank templates and completed BOMs by content. Zips are extracted safely, including nested ones (zip-slip blocked).
- **Batch** (`batch` command): one job per sub-folder, with `BATCH_SUMMARY.xlsx`.
- **Deep check**: about 40 checks with severity, affected BOM lines, fix instructions and coordinates. Results go to the `Deep Check` audit sheet, `*_ISSUES.csv` and `*_ISSUES.scr` (an AutoCAD script that circles each issue with object snaps off).
- **Policies**: every open convention is computed every way. With an approved BOM, each option is scored per cell; `--learn` stores the evidence in `config/policies.json` and selects the best. On a tie, the documented design standard / AutoCAD-routine method wins over the lower total error. The Credit River calibration confirms all current defaults.
- **Splice Guide report layout** ("Fiber Optic Splice Guide") is parsed. Before this, three NMK-R03 reports were read as blank enclosures with 0 splices.
- `pipeline.run_job()` is shared by the CLI, batch and the app. The CLI has `run` / `auto` / `batch` / `app` sub-commands; the old flag form still works.

### Bugs found by the new self-tests (each has a regression test)
- A new cable dataclass field shifted positional arguments, so a report-only cable got text in `path_ft`. All constructor calls now use keywords.
- The app's issue table needed `jinja2` (not installed with Streamlit), so the results page crashed. It now uses plain markers.
- The batch summary showed job-wide issue totals on every OLM row. It now counts per BOM.
- Deprecated Streamlit `use_container_width` replaced with `width="stretch"`.

## 0.3.0 - FX_DROPS / CalcFTG routines, blank per-OLM template
- **Drop footage** (row 11) now computed from the FX_DROPS lines on `RTE_SpatialNet_UGDROP` (ped edge to address PED, CX1-FTG-N2 length). Each drop follows the address it serves. The row carries Non-Grant drops only, matching the reference "total - grant"; grant drops are shown in the audit. If a network has no drop lines, the row is left blank with a "run FXAUTO" warning. NMK-R03 Non-Grant 52,752 vs reference 52,678 (0.14%); DMI-R15 222 drops = 222 passings, 36,117 ft = label sum.
- **Splice trays**: trays per location ROUNDUP(splices/48 or /24), then 2-tray packages pooled per column. Reproduces the reference 450D R02 4 / R04 4 / R05 5 and 450B 1/1/2 (R03 5 vs 4).
- **MAX10 +4 upgrade kits**: need-based (a kit per 4 passings a ped feeds above its 4 stock ports, HC/CC association as in FX_DROPS). No ped in NMK or DMI feeds more than 2, so 0. The reference's 44/63 and the template's `=I19` are a blanket policy; flagged for confirmation.
- **Blank per-OLM template** (4 area columns): area columns are detected from the header. The CLI writes one BOM per OLM when the job has more networks than columns. Transport BOM columns and Jumper Calculator blocks are detected by structure.
- Template formulas that are inconsistent across area columns are repaired from the first column and logged (new template: I-K28 summed the GOAT peds, I-K29 was x2). Template formulas replaced by computed values are logged (SFP, splitters, power IFs, MAX10 upgrade).
- A per-network value that was not computed now stays blank instead of 0.
- NMK reconciliation: 292/360 cells, 156/180 network totals.

## 0.2.0 - design standards (see DESIGN_STANDARDS.md)
- Splice trays (450B/450D) now computed: per location ROUNDUP(ROUNDUP(fusion splices / 24 or 48) / 2) packages. NMK: R02, R04 exact; R03/R05 one package higher than the reference (reference pools small locations).
- SFP = ROUNDUP(Jumper Calculator splitters / 2) per column (identical on NMK; DMI-R15 now 5 instead of 8).
- OLM equipment booked to Grant unless the OLM area has no grant passings.
- Splitter totals use the designed count from the splice reports when available.
- NMK reconciliation: 291/360 cells, 154/180 network totals (was 287/150).

## 0.1.0 - first working build

### Implementation
- DWG extraction via LibreDWG/WebAssembly (`tools/dwg2json.mjs`, pinned `@mlightcad/libredwg-web@0.8.0`), cached by file hash. LibreDWG read status is surfaced, not hidden (NMK: non-critical 68 = UNHANDLEDCLASS|VALUEOUTOFBOUNDS).
- DXF backend (ezdxf) with the same normalized model.
- Proxy-graphics decoder (DWG bit-stream LWPOLYLINE, opcode 33) for SpatialNet `LWPolygon` Non-Grant boundaries, which are stored only as ACAD_PROXY_ENTITY objects.
- Address-list and splice-report readers. Fusion splices are separated from pass-through fibers.
- Takeoff engine: networks, transport corridor, Grant/Non-Grant, passings, peds, vaults, cable routing with span-based Grant split, enclosures, splitters with a data-driven split ratio, OLM equipment.
- Rule catalogue (`config/bom_rules.json`) and evaluator. A missing quantity is never silently 0.
- Template writer: clears reference-project constants (typed numbers and constant formulas like `=3+1`), keeps cell-referencing formulas, restores the x14 `System:` list validation that openpyxl drops.
- Verification: reopens the output, checks structure (parts/descriptions/F-G formulas), cell placement and duplicate mapping, then recalculates with LibreOffice and checks for Excel errors and that G equals the column sum.
- Audit and discrepancy workbooks, coverage summary.

### Calculation changes found by self-testing
- Cable Grant split: switched from the length-inside-polygon fraction to majority area per splice-to-splice span. This reproduces R03 FC048 exactly and lowers the total split error.
- Passings must use strict boundary containment. With nearest-network assignment, an aerial house-count block 81 ft outside R04 made it 217 vs 216 in the address list.
- Transport corridor: objects go to the network fed by the OTN transport cable, not to whichever network is nearest. Before, corridor route labels were split between R02 and R04.
- Cables present in the splice reports but carrying no drawing label (100 ft OLM tails) are now included and flagged.

### Bugs fixed (each has a regression test)
- Grant address matching failed on directional prefixes ("23955 N BEARD AVE" vs block "BEARD"). R02 grant residential dropped from 17 to 14. `test_address_tokens_directionals_regression`.
- Grant matching required a numeric house number, which excluded served unnumbered or vacant locations in DMI-R15 ("78TH AVE AVE", "VAC 708 RUTLEDGE ST"). `test_address_tokens_unnumbered_and_commercial_regression`.
- Splitter ratio was hard-coded to 1x64. DMI-R15 uses 1x32: 7 couplers, 7 PONs. `test_split_ratio_sources`, `test_dmi_internal_consistency`.
- Duplicate cable labels with identical values were reported as FAIL. They are now WARN, and FAIL only when the values conflict.
- openpyxl read-only parsing leaked "Data Validation extension" warnings. Runtime dropped from 290 s to about 145 s by loading the 90 MB template sheet once and using read-only grids for verification and the reference.

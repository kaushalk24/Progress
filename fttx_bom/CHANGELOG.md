# Changelog

## 0.6.0 - Melcher-Dallas approved BOM: SME Grant/Non-Grant rule, RF plant left out

Reconciled against the manual DMI-R15 BOM (see FORENSIC_FINDINGS.md "Melcher-Dallas"): 72 → 75 of 90 cells, 34 → 38 of 45 totals.

- **RF (coax) support structures are not calculated (SME):**
  - vaults/L-boxes at an RF device with no fiber splice nearby are left out (DMI: 1 vault, now 8 = approved);
  - aerial strand with no aerial fiber cable is left out (DMI: 512 ft, now 0 = approved);
  - RF devices are never reported as unmapped materials.
- **SME Grant/Non-Grant rule** (Non-Grant inside the boundaries, Grant = total − Non-Grant):
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
- **Credit River effect:** 8 cells now follow the SME rule and the DMI convention instead of the Credit River practice (SFP Grant 3, MAX10 +4 3, Grant drops 2).
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
- **Policies**: every open convention is computed every way. With an approved BOM, each option is scored per cell; `--learn` stores the evidence in `config/policies.json` and selects the best. On a tie, the documented SME / AutoCAD-routine method wins over the lower total error. The Credit River calibration confirms all current defaults.
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

## 0.2.0 - rules from the SME BOM walkthrough (see SME_MEETING_NOTES.md)
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

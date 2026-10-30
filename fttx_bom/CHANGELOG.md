# Changelog

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

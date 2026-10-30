# Progress and issues

_Last updated: 2026-10-30, build 0.1.0_

## Working

- End-to-end CLI: DWG (AutoCAD 2018 / AC1032 read natively via LibreDWG-WASM) or DXF, plus address lists, splice reports and the template, produces FINAL_BOM, BOM_AUDIT and BOM_DISCREPANCIES.
- NMK-R02..R05 combined run: 142 s. DMI-R15 run: 95 s. Both exit 0 with no engine or workbook failures. Formulas were recalculated with LibreOffice and checked (no Excel errors; G = sum of the area columns; recalculated totals = engine totals).
- Template fidelity: sheets, part numbers, descriptions, F/G formulas, comments, external links and conditional formatting are preserved. The B1 list validation is restored. Reference-job constants are cleared from the area columns.

## NMK reconciliation (reference = manual Credit River BOM)

| Measure | Result |
|---|---|
| Area cells compared | 360 |
| Area cells matching | 292 |
| Network totals matching | 156 / 180 |

Lines reproducing all 8 Grant/Non-Grant cells: residential, commercial and MDU passings; Z-14 OLM ped; OLM bundle; XGS SFP+; 1x64 and 1x32 splitters; MDU enclosure; FOSC 450A/C/D; OLM power equipment; batteries; FC072, FC144 and zero-quantity cable sizes; Transport BOM; Jumper Calculator.

Lines with exact network totals but a different Grant/Non-Grant split: MAX10 and MAX5 peds, vaults, 450B, FC048, FC096 and FC024 (R02/R03). The cause is objects or spans close to Non-Grant polygon edges. In R05 the shift is consistent across rows, which suggests the boundary changed after the manual BOM.

## Remaining issues (ranked by effect on BOM correctness)

1. **Drop footage:** now computed from the FX_DROPS lines. It needs FXAUTO run and saved in every network's drawing; R02/R04 in the combined file have no drops, so they're flagged.
2. **Route / UG footage (rows 6-10): INFERRED.** The tool uses the trench route-footage labels. The reference uses a different method in each network (R04/R05 cable sums incl. slack; R02 ≈ route; R03 neither). *Decision needed:* which definition is approved.
3. **Reference cable errors to confirm:** R04 has 5,187 ft moved from FC024 to FC048 against both the drawing and the splice reports. The 100 ft OLM tail is counted in R02/R03 but not in R04/R05.
4. **Trays:** 6 of 7 network totals exact with pooled packages. **MAX10 +4:** need-based gives 0 (no ped feeds more than 2); the reference and template apply a blanket policy, so this needs SME confirmation.
5. **Grant/Non-Grant split near boundaries.** Location-based classification is verified as the method, but a few items sit within a few feet of edges. *Need:* confirmation that the current DWG Non-Grant polygons are final (R05 especially).
6. **SFP convention.** The reference rounds each area separately, giving 18 SFP for 15 PONs. The tool reproduces this and flags it.
7. DMI-R15: 6 cable segments can't be routed because one end (DMI-14001G, DMI-16249G, 15222G, 15091G, 15029) has no splice symbol or splice report. Those segments are classified at their label point and flagged.
8. DMI-R15: the drawing house counts (223) exceed the address list (222) because of a duplicate "2023 60TH" address block. The address list is used.

## Tests

`python -m pytest -q` → 25 passed (12 unit, 12 integration on the real files, 1 end-to-end CLI on DMI-R15). The integration tests need `FTTX_TEST_DATA` to be set.

## Next priorities

1. Get the drop-footage and route-footage definitions from engineering, then implement and verify them.
2. Add tray rules once the engineer confirms the tray capacity and spare policy.
3. Optional: a simple GUI or a Windows batch launcher.

## Pending from the SME meeting
- The marked-up template showing which cells to fill.
- Grant address validation report: a separate deliverable, not built yet. Needs its template (see SME_MEETING_NOTES.md #13).

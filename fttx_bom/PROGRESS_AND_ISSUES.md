# Progress and issues

_Last updated: 2026-10-31, build 0.6.0_

## Working

- **Self-service tool:** local app, `auto` and `batch` commands, deep check with an AutoCAD issue script, and policies learned from approved BOMs (0.4.0).
- **0.5.0, forensic and review release:**
  - **New rules:** ground wire kits from the template note, D basket = 0, and a second split ratio written.
  - **New design checks:** ped size against cable, closure capacity, cross-network cables.
  - All 19 findings of an independent code review are fixed or documented, each with a regression test.
- **Per-OLM runs on a combined drawing** now give the same numbers as the combined run, cell for cell. They used to book neighbours' objects and the transport corridor to the job network.
- **Template layout:** the area columns are found from the header, and a template is split into one BOM per OLM whenever its Transport BOM or Jumper Calculator can't hold more.
- **Outputs:** every output is marked, so a rerun never treats the tool's own BOM as the approved BOM.

## DMI-R15 reconciliation (reference = manual Melcher-Dallas BOM, 0.6.0)

| Measure | 0.6.0 | 0.5.0 |
|---|---|---|
| Area cells matching | **75 / 90** | 72 / 90 |
| Network totals matching | **38 / 45** | 34 / 45 |

**Fixed:**
- RF strand and the RF vault are no longer counted (aerial 0; vaults 8);
- SFP 1 / 3 and MAX10 +4 0 / 9 now come from the design standard and the template formula;
- ground kits are left blank, as in the BOM.

**Manual-BOM errors found:**
- FC024 is double-counted (+6,467 ft, a duplicated drawing label);
- row 6 has footage typed into the mileage row;
- the bonding jumper and ped bonding kit use the template's inconsistent column formulas.

**Open:**
- UG footage −1.8%;
- D trays 5 against 4;
- one MAX5 split;
- the drop-column convention.

See FORENSIC_FINDINGS.md D1–D14.

## NMK reconciliation (reference = manual Credit River BOM)

**0.6.0:** 290 / 368 cells, 156 / 184 totals. The 8 cells fewer than 0.5.0 are where the defaults now follow the design standard and the DMI BOM instead of the Credit River practice: SFP Grant 3, MAX10 +4 Non-Grant 3, Grant drops 2. Nothing else changed. The table below is the 0.5.0 history.


| Measure | 0.5.0 | 0.4.0 |
|---|---|---|
| Area cells matching | **298 / 368** | 292 / 360 |
| Network totals matching | **160 / 184** | 156 / 180 |
| Like-for-like (0.4.0 lines only) | 290 / 360 cells, 156 / 180 totals | — |

**Why the like-for-like figure is 2 cells lower:** the 0.4.0 discrepancy report compared route-mileage cells with a 0.5 tolerance, so differences up to half a mile counted as matches. It now uses 0.01 mi, as calibration does. No quantity changed.

**Exact quantity check:** every takeoff quantity was compared between 0.4.0 and 0.5.0 on NMK and on DMI. The only changes are the two new lines:
- ground kits: Credit River reference blank, so 0/8 by design;
- D basket: 8/8.

**Lines reproducing all 8 Grant/Non-Grant cells (30 BOM lines):**
- passings, Z-14 ped, GOAT and tap peds (0);
- FC072, FC120–FC288, FOSC 450A/C/D, D basket;
- OLM bundle, XGS SFP+, 1x32 and 1x64 splitters;
- MDU enclosure, OLM power equipment and batteries;
- plus the Transport BOM and Jumper Calculator sheets.

**Exact network totals, different Grant/Non-Grant split:** MAX10 and MAX5 peds, vaults, 450B, FC096, B trays. These are objects or spans within a few feet of Non-Grant edges. R05 shifts the same way on every line, which suggests the boundary was edited after the manual BOM.

**Not reproducible or reference errors:**
- UG and route footage split (F4);
- FC024 and FC048 in R04 (reference error, F8);
- drops (R02 and R04 have no drop lines);
- MAX10 +4 (blanket policy in the reference);
- heat shrink (not filled in, per the design standard).

See FORENSIC_FINDINGS.md for the line-by-line table.

## Critical unresolved issues (deliverable G), ranked by effect on BOM correctness

0. **Drop-footage columns: decision needed.** The two approved BOMs disagree:
   - Credit River puts Non-Grant drops only in the Non-Grant column.
   - Melcher-Dallas puts the whole drop footage there.
   - The design standard (Non-Grant inside, Grant = total − Non-Grant) gives the split. It is the new default; the other two are options.
1. **Route / UG footage split (rows 6–10).**
   - Network totals follow CalcFTG.
   - The reference Grant/Non-Grant split can't be reproduced by any geometric method (FORENSIC_FINDINGS F4).
   - *Decision needed:* confirm the current Non-Grant polygons, especially R05, and which footage definition is approved.
2. **MAX10 +4 upgrade kits.**
   - The default is now the template formula (one kit per Non-Grant MAX10), as in the DMI BOM.
   - Credit River used a different blanket (44 / 63), and need-based gives 0.
   - *Decision needed:* which policy applies (F7).
3. **Ground wire kits.**
   - Both approved BOMs leave the line blank, including DMI on the template with the note, so it is no longer written.
   - The audit shows the hand count (DMI 126, NMK 321).
4. **Hub closures over tray capacity.**
   - NMK-02001G and 03001G need 6 D trays; the 2004 ordering guide gives 5 for a T3V closure.
   - *Confirm:* the closure configuration, or the current CommScope limit (vendor site blocked here).
5. **Reference cable errors to confirm:** R04 has 5,187 ft moved from FC024 to FC048, and the OLM tail is inconsistent (F8).
6. **Grant/Non-Grant split near boundaries.**
   - Items within a few feet of the Non-Grant edges.
   - The R05 boundary probably changed after the manual BOM.
7. **Drop footage** needs FXAUTO run and saved in every network's drawing; R02 and R04 in the combined file have no drops.
8. **DMI-R15:**
   - 6 cable segments have one end without a splice symbol or splice report, so they are classified at their label;
   - there is a duplicate "2023 60TH" address block.
9. **Learned-policy evidence** is keyed by project number and network names. Two projects with the same keys would overwrite each other's evidence (review finding 18, minor).

## Tests

`python -m pytest -q` (with `FTTX_TEST_DATA`):
- 77 tests: 76 run without the slow end-to-end test, which is run before a release;
- unit, tooling, forensic-rule and review-regression tests;
- integration on the real NMK / DMI files;
- the end-to-end CLI run.

## Related deliverables

- Grant address validation report: a separate deliverable, not built yet (DESIGN_STANDARDS.md).

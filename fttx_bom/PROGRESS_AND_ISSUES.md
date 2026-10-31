# Progress and issues

_Last updated: 2026-10-31, build 0.5.0_

## Working

- **Self-service tool:** local app, `auto` and `batch` commands, deep check with an AutoCAD issue script, and policies learned from approved BOMs (0.4.0).
- **0.5.0, forensic and review release:**
  - **New rules:** ground wire kits from the template note, D basket = 0, and a second split ratio written.
  - **New design checks:** ped size against cable, closure capacity, cross-network cables.
  - All 19 findings of an independent code review are fixed or documented, each with a regression test.
- **Per-OLM runs on a combined drawing** now give the same numbers as the combined run, cell for cell. They used to book neighbours' objects and the transport corridor to the job network.
- **Template layout:** the area columns are found from the header, and a template is split into one BOM per OLM whenever its Transport BOM or Jumper Calculator can't hold more.
- **Outputs:** every output is marked, so a rerun never treats the tool's own BOM as the approved BOM.

## NMK reconciliation (reference = manual Credit River BOM)

RECON_TABLE

## Critical unresolved issues (deliverable G), ranked by effect on BOM correctness

1. **Route / UG footage split (rows 6–10).**
   - Network totals follow CalcFTG.
   - The reference Grant/Non-Grant split can't be reproduced by any geometric method (FORENSIC_FINDINGS F4).
   - *Decision needed:* confirm the current Non-Grant polygons, especially R05, and which footage definition is approved.
2. **MAX10 +4 upgrade kits.**
   - The need-based count is 0; the reference applies a blanket policy (44 / 63).
   - *Decision needed:* which policy applies (F7).
3. **Ground wire kits.**
   - Now written from the template note (NMK 321, DMI 126).
   - *Confirm:* that new BOMs should order them; the Credit River BOM left the line blank. `ground_kits=not_ordered` restores the blank.
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
- TEST_COUNT
- unit, tooling, forensic-rule and review-regression tests;
- integration on the real NMK / DMI files;
- the end-to-end CLI run.

## Pending from the SME meeting

- Grant address validation report: a separate deliverable, not built yet (SME_MEETING_NOTES.md #13).

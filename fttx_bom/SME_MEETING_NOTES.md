# SME BOM walkthrough (meeting recording, 34 min)

Transcribed locally with Whisper (small.en). Timestamps refer to the recording. Each rule is listed with how the tool handles it.

| # | What the SME said | Tool |
|---|---|---|
| 1 | [02:46] Z-14 OLM ped: "1 per OLM, under the grant column only, by default". [15:17] The same applies to the OLM equipment and power supplies. [15:46] If the whole OLM area is Non-Grant, everything moves to Non-Grant. | OLM items go to Grant when the network has any grant passings, otherwise to Non-Grant. |
| 2 | [03:14] MAX5 and MAX10 peds: count those within the OLM boundary and split them by the Grant/Non-Grant boundary. | Location against the Non-Grant polygons (already the rule). |
| 3 | [04:31] Vaults: count within the OLM boundary, split by area, any size. [05:14] Proposed only; existing vaults are not counted. | Counts `CX1-VAULT`. Check that existing vaults never use this block. |
| 4 | [05:30] Rows with predefined formulas (bonding jumper, kits, ped trays) are left as they are. | Template formulas kept. |
| 5 | [05:58] Fiber cable: use the design length (not the route length), split Grant/Non-Grant manually along the cable, and include slack loops (e.g. 15 ft at a ped). [07:53] The totals must equal the splice-report design length per fiber count. [08:35] The top footage/mileage rows must match the fiber drafting route length. | Cable = label TOTAL (design length), cross-checked against the splice reports. Split by routed spans. Footage rows = route labels. |
| 6 | [08:54] FOSC 450B/450D: how many are used. | From the splice reports. |
| 7 | [09:17] Burns & heat shrink: not updated. | Left blank (audit only). |
| 8 | [09:23] Taps: only the FTTx MDU enclosure is used (the design uses fiber bulkheads). ONU is not updated. | 1 MDU enclosure per MDU building. Tap rows blank. |
| 9 | [10:47] SFP: take Jumper Calculator "Splitters Required" for each column, divide by 2 and round up, e.g. 7/2 → 4. "Don't confuse with what splitter you actually use." | `ROUNDUP(ROUNDUP(passings/32)/2)` per column. |
| 10 | [13:32] Splitters: the designed count (R02 = 4). Put 1 under Grant ("it feeds some grant address"); the rest go to Non-Grant. | Designed count from the splice reports. Grant = `ROUNDUP(grant/ratio)`, Non-Grant = rest. |
| 11 | [18:01]–[27:50] Splice trays: 450B/450D come without trays. For each splice location, count the splicing: homes + power port + transport fibers (own and other node) + splitter legs. 02001G = 242. 450D tray = 48 splices, 450B tray = 24. Calculate location by location: `242/48` → 3 packages ("order 2 per package"). Leftover trays may be reused at another location. | Per location `ROUNDUP(ROUNDUP(splices/cap)/2)`. Fusion-splice counts from the splice reports equal the SME's 242. |
| 12 | [28:30] They will share a template that marks which cells must be filled. | Pending. |
| 13 | [29:56]–[34:00] Final deliverable: **grant address validation report**. Starts from the fiber-drafting grant validation report; add the Non-Grant addresses; remarks for field-verified differences. Grant addresses are never changed (comment only); Non-Grant addresses are corrected in SpatialNet with the comment "followed correct street number". Light yellow = grant, orange = Non-Grant. Filter by OLM. | Not implemented yet: a separate deliverable. Needs the validation-report template. |

Not covered in the meeting: drop footage source, MAX10 +4 upgrade kits, tray pooling policy.

## AutoCAD routines supplied afterwards

- **FX_DROPS_v9.lsp** (`FXPED`, `FXAUTO`, `FXDROP`, `FXMISSING`, `FXLABEL`, `FXCHECK`):
  - Places a `PED` block 6.6 ft off every address, on the side facing its feeding ped.
  - Draws one straight drop per address on `RTE_SpatialNet_UGDROP`, from the edge of the feeding MAX5/MAX10 box to that PED.
  - Labels each drop with a `CX1-FTG-N2` FTG rounded to the nearest foot. Drops longer than 1,500 ft are not drawn.
  - MDU addresses get no drop. Peds never get more drops than their `CX1-COUNT` house count.
  - **The tool reads these lines for row 11**, so FXAUTO must be run and saved before the BOM. The tool warns when a network has no drops, or when the drop count differs from the non-MDU passings (the same check as FXMISSING).
- **CalcFTG_3_1_2.LSP**: pick a closed boundary, then it sums `CX1-FTG-N2` FTG labels fully inside it (window polygon), separated by layer `GRANT FTG` / `NON-GRANT FTG` / `RTE_UGTRENCH`. This is how rows 6-10 were filled. The tool uses the same labels, with the OLM boundary and the Non-Grant polygons standing in for the manual selection.

## Blank BOM template (NewPeds ... FTTH_BOM_1.27.26)

- **One OLM per BOM**, with 4 area columns (H-K). The tool writes one BOM per OLM.
- **Formula bugs in the template**, repaired and logged in the audit:
  - I28-K28 `=SUM(x21:x22)` should be `=SUM(x19:x20)*2`.
  - I29-K29 are `*2` but should be `*1`, as in column H and the reference.
- **Default formulas the tool overrides** with SME / data-based values (logged):
  - SFP and 1x64 splitter `=ROUNDUP(x12/64)` per column.
  - MAX10 upgrade `I23=I19`.
  - Power-supply `IF(H18…)`.

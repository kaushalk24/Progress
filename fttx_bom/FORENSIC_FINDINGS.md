# Forensic reconstruction of the Credit River (NMK-R02..R05) BOM

This is deliverable A: what each line of the approved BOM is, how it was built, and how far the tool reproduces it from independent sources (drawing, address lists, splice reports, template notes). The reference totals are never hard-coded; they are only used for comparison.

The per-line table at the end is generated from the tool's own discrepancy workbook (`*_BOM_DISCREPANCIES.xlsx`) for the 0.5.0 run.

## Method

For every line, several hypotheses were tested against the drawing entities, each one computed every way (forensic scripts and the tool's policy variants), and scored cell by cell against the approved BOM:

> DWG entity or design condition → engineering interpretation → component → assembly → formula → BOM quantity

A hypothesis is accepted only if it:
- reproduces the reference from independent data;
- or is stated by the customer's template or the design standard;
- and generalises to the second design (DMI-R15).

Blank and zero lines were treated as evidence too: a blank line may mean "not ordered", "not filled in", or "not applicable".

## Findings by investigation

### F1. Ped type against cable size: a design rule, not a BOM formula

- **Hypothesis (rejected):** a template rule "MAX10 above 72F, MAX5 at 48F or less". It is not in the template; it was a hypothesis, and 60 NMK and 47 DMI MAX10 sit on cables of 48F or less.
- **Verified pattern:** a MAX5 **never** houses a splice on a cable above 48F, whether mid-span, branch or end.
  - Mid-span peds on cables above 48F: NMK 0 MAX5 against 113 MAX10; DMI 0 against 11.
  - Each splice is tied to its nearest housing (ped, vault or L-box), and splices in FOSC closures are excluded.
  - The first count found 5 MAX5 "branch" cases in NMK; 4 of them were the OLM hub splices, which sit in a FOSC 450D next to a MAX5.
- **Interpretation:** a mid-span access on a large cable needs room for the express buffer tubes and slack, so the larger MAX10.
- **In the tool:** WARN MAX5_ON_LARGE_CABLE, plus INFO MAX10_SMALL_CABLE (NMK 1, DMI 3). Ped counts stay the block counts (network totals 8/8 exact).

### F2. Ground wire kits (FE0-07264810): new line

- **Reference:** blank in every column. Credit River used the older template, which has no note.
- **Customer spec:** the blank template (NewPeds 1.27.26) says in L27: "Hand count for Grounds: All splices with letter G at End, First in line, any ending in a zero, and also EOL Peds".
- **Hypotheses tested:**

| Hypothesis | NMK count | Notes |
|---|---|---|
| G suffix only | 248 | |
| G or end of line | 249 | G and end of line coincide for 243 of 248 |
| Template union, "first in line" = the cable's B end | 319 | |
| **Template union, "first in line" = first splice on the routed path from the OLM hub** | **321** | Adopted: it matches "first in line" physically |

- **"First in line":**
  - The hub is the splice point nearest the OLM block, 63–132 ft away.
  - The routed cable paths pass through the splice points exactly (0 ft).
  - NMK: 02002, 02119, 02120, 03002, 03092, 03129, 04002, 04117, 04217, 05002 and 05117. DMI: DMI-15002G, DMI-15116G and DMI-15171.
- **Interpretation (inference; no public rule found, see RESEARCH.md §5):**
  - Grounding at the first ped, at regular intervals (names ending in 0 are roughly every tenth splice) and at the ends of line.
  - This is the usual pattern for bonding a metallic cable element at its ends and at intervals.
  - The G suffix marks the designer's planned ground locations.
- **Result:** NMK R02 70, R03 85, R04 87, R05 79; DMI 126. Policy `ground_kits` reproduces the reference blank with `not_ordered`.
- **Confidence:** Medium. The rule is the customer's own; whether the Credit River team would have ordered these kits is unknown.

### F3. Cable Grant/Non-Grant split: 8 hypotheses

The test is the absolute Non-Grant error over the 12 R02/R03 cells that the reference split by hand.

| | Method | Error (ft) | Exact cells |
|---|---|---|---|
| **H1** | Routed span majority, split at splices and structures (the tool) | **2,497** | **8** |
| H2 | Routed length inside the Non-Grant polygons | 4,126 | 7 |
| H3 | Whole cable by majority length | 5,203 | 8 |
| H4 | Whole cable by its B-end location | 20,968 | 8 |
| H5 | Whole cable by its A-end location | 66,617 | 7 |
| H6 | Whole cable by its label location | 59,579 | 5 |
| H7 | Route-footage labels along the path | 2,497 | 8 (identical to H1) |
| H8 | Share of the served addresses the cable carries (BEAD passings allocation) | 86,323 | 0: **rejected** |

**Conclusion:** the manual split is geographic, by span, not by passings. H1 stays the default; H2 is the `length` policy option.

### F4. Route footage rows 6–10

- **Network totals:**
  - R02, R03 and R05 equal the sum of CX1-FTG-N2 labels (the CalcFTG method).
  - R04 includes the transport corridor differently from the reference.
- **Grant/Non-Grant split:** three methods all fail to reproduce the reference:
  - label point in polygon;
  - CalcFTG window (label wholly inside);
  - trench length inside the polygons.

  | Network | Reference G/NG | Every method gives about |
  |---|---|---|
  | R02 | 41,180 / 37,837 | 42.2k / 36.6–36.8k |
  | R03 | 42,398 / 57,710 | 45.7–46.2k / 53.9–54.4k |
  | R05 | 89,443 / 41,501 | 111.1k / 19.8–19.9k |

  - R05's shift is about 21,600 ft in the same direction on every method. Ped, vault, 450B and cable cells all shift the same way in R05, which points to the Non-Grant boundary being edited after the manual BOM.
- **Label-to-trench matching (for a stale-label check):**
  - 95 labels have no trench match, 158 polylines have more than one label, and 271 polylines have none.
  - Shipping a check on this basis would mostly give false alarms, so it was **not** shipped.
- **Status:** INFERRED; both definitions remain policy options.

### F5. Label geometry (supports F3 and F4)

- Route FTG labels sit about 5 ft from the trench polylines; cable polylines are offset about 25 ft.
- Label FTG against trench length: median difference about 0, with outliers up to −881 ft. Labels can be stale after edits, which is a design-QA item.

### F6. Splice trays and closures (research-backed)

- **Ordering guide** (RESEARCH.md §1): kits have SOQ 2, each holding 2 trays; a B tray takes 24 splices and a D tray 48. This confirms the package rule (6 of 7 reference network totals exact).
- **D basket = 0:** the T3V closure includes its tall basket. Reference 0 → VERIFIED.
- **Over capacity:** NMK-02001G (242 splices) and NMK-03001G (255) need 6 D trays. The 2004 guide allows 5 in a T3V (tall basket) → WARN CLOSURE_OVER_CAPACITY. The current datasheet could not be opened.

### F7. MAX10 +4 upgrade kits

- **Need-based (ports used above 4):** 0, because no ped in NMK or DMI feeds more than 2 passings.
- **Reference:** 44 / 63 = every MAX10 in R03 Grant and R04 Grant only. The new template defaults to the MAX10 count. Both are blanket policies.
- **Status:** unresolved, so the policy options stay (need_based is the default). No public RaDD specification could be opened.

### F8. Reference BOM errors (unchanged; independently confirmed)

1. **NMK-R04:** the reference moves 5,187 ft from FC024 to FC048. The drawing labels and the splice reports agree with each other, not with the reference.
2. **OLM tail:** the 100 ft FC024 OLM tail is counted for R02/R03 but not R04/R05.
3. **Rows 6–10:** a different method in each network.
4. **Drop rows:** typed "total − x" values.

## Blank and zero lines

| Line | Reference | Meaning found | Tool |
|---|---|---|---|
| FE0-07264810 ground kit | blank | Older template, not filled in | Writes the template-note count; reference blank is not taken as evidence (calibration skips all-blank rows) |
| FE0-R89279 D basket | 0 | The T3V includes its basket | 0 (VERIFIED) |
| FM0-FF11002 heat shrink | blank | design standard: not updated in the BOM | Blank; the audit shows splices |
| FOSC 450A / 450C | 0 / blank | No such enclosure in the reports | 0 when reports exist; blank without reports |
| GOAT peds, taps, MST, plenum lateral | 0 / blank | No symbol in the design | Blank, NOT_DETECTED |

## Melcher-Dallas (DMI-R15): reconstruction of the manual BOM (0.6.0)

The manual DMI-R15 BOM was supplied after 0.5.0. It uses the new blank template, with the sheet renamed "OLM DMI-R15 BOM". Two design rules apply:
- **RF support structures are not calculated.** The design also contains RF (coax) plant: an amplifier, an RF power supply, a tap, a terminator, an end-of-line marker, 3 poles, strand, an anchor and a riser.
- **Grant/Non-Grant:** Non-Grant = everything inside the Non-Grant boundaries; Grant = total − Non-Grant.

| # | Line | Manual BOM | Drawing / tool | Finding | Status |
|---|---|---|---|---|---|
| D1 | Aerial footage | 0 | 512 ft on 3 strand labels | The strand carries no fiber: there are no aerial fiber cables in DMI at all. It is RF strand on the amplifier/power-supply poles. Strand now counts only with an aerial fiber cable within 75 ft; NMK is unchanged, since all 30 of its strand labels are within 53 ft of aerial fiber. | **Fixed, matches** |
| D2 | Vault CBV-HGIB2436 | 8 (7/1) | 9 drawn | Vault 3CC8B7 is 31 ft from the RF amplifier, with no fiber splice within 309 ft. It is RF support. Rule: RF device within 50 ft and no splice within 100 ft. RF power supplies don't count as evidence, because the coax-powered OLM hub vault sits beside one. NMK is unaffected. | **Fixed, matches** |
| D3 | FC024 | 147,111 | 140,644 (= splice reports) | "DMI-14001G TO DMI-15204G FC024" is labelled twice with identical values (6,467 ft). The manual BOM summed both labels; the reports list the cable once. | **Manual BOM error (+6,467 ft)** |
| D4 | XGS SFP+ | 1 / 3 | was 2 / 3 | The manual BOM follows the design standard: Non-Grant = ROUNDUP(155/64) = 3 (template formula), Grant = ROUNDUP(222/64) − 3 = 1. This is now the default. On NMK it gives 15 SFP = 15 designed PONs; the Credit River BOM's per-column rounding gave 18. | **Fixed, matches** |
| D5 | Splitters 1x32 | 3 / 4 | 3 / 4 | Grant = ROUNDUP(67/32) = 3, Non-Grant = 7 designed − 3. Both approved BOMs compute Grant first for splitters, so this stays the exception to the Non-Grant-first rule. | Matches |
| D6 | MAX10 +4 kits | 0 / 9 | was 0 / 0 (need-based) | The manual BOM keeps the template formula I23 = I19: one kit per Non-Grant MAX10. This is now the default. | **Fixed, matches** |
| D7 | Ground wire kit | blank | was 77 / 49 | Left blank, although the template carries the hand-count note. It is no longer written; the audit keeps the count. | **Fixed, matches** |
| D8 | Passings | 67 / 142, 0 / 13 | identical | The Non-Grant-inside rule gives exactly the same split in DMI. In NMK, 25 served addresses on the plain Address layer lie outside every Non-Grant polygon, and the Credit River BOM follows the layer. So the passings rule stays layer-based, and the new WARN ADDRESS_LAYER_VS_BOUNDARY lists every disagreement. | Matches |
| D9 | Drop footage | NG 35,941, G blank | 36,117 total: G 10,194 / NG 25,923 | The whole drop footage went into the Non-Grant column. Credit River put only Non-Grant drops there. The design standard (Non-Grant inside, Grant = total − Non-Grant) gives 10,194 / 25,923, which is the new default. The other two are options (`total_nongrant`, `nongrant_only`). | **Conflict, to confirm** |
| D10 | UG footage | 165,584 / 51,957 | 169,182 / 52,335 | −1.8%. The Non-Grant gap is exactly two labels (250 + 128 ft). One 2,374 ft trench label has no fiber cable within 1,200 ft (INFO TRENCH_NO_FIBER; policy `fiber_bearing`). The rest can't be reproduced because label-to-trench matching is ambiguous. | Open |
| D11 | Row 6 "Total Route Mileage" | 165,584 / 51,957 | 32.14 / 9.91 mi | The manual BOM typed footage into the mileage row; row 7 holds the miles (31.36 / 9.84). | **Manual BOM unit error** |
| D12 | D trays FE0-R579575 | 5 | 4 | DMI-15001G has 234 splices → 5 trays; DMI-15019 has 93 → 2. That is 7 trays → 4 kits of 2. No splice-count rule gives 5, and Credit River R03 goes the other way (4 against 5). | Open |
| D13 | MAX5 split | 86 / 61 | 85 / 62 | Network total matches. One ped is inside a Non-Grant polygon in the current drawing. Window-selection edge tests don't reproduce it: NMK and DMI differ in opposite directions. | Boundary edit |
| D14 | Bonding jumper / ped bonding kit | NG 0 / 140 | NG 140 / 70 | The manual BOM inherits the template's inconsistent column formulas: I28 = SUM(I21:I22) sums the GOAT peds, and I29 = SUM(I19:I20)*2. The tool repairs them to match the Grant column (2 jumpers and 1 kit per ped). **Please fix the master template.** | Template bug |

**Score:** 72/90 → **75/90** cells and 34/45 → **38/45** network totals.

**Effect on NMK:** the new defaults for SFP, MAX10 +4 and drops follow the design standard and the DMI BOM, not the Credit River practice. This costs 8 NMK cells (SFP Grant 3, MAX10 +4 Non-Grant 3, Grant drops 2). Nothing else changes. Each old convention is still an option, and `--learn` picks whichever the approved BOMs support.

## Per-line table (0.5.0 run against the Credit River approved BOM)

<!-- generated from the discrepancy workbook by the forensic script; do not edit by hand -->

The run covered 368 area cells and 184 network totals: **298 cells and 160 network totals match**. The like-for-like figure on the 0.4.0 lines is 290 of 360. The two cells fewer are mileage cells that the old 0.5-mile tolerance had wrongly counted as matching.

| BOM line | Rule status | Reconstructed formula | Reference R02/R03/R04/R05 | Tool R02/R03/R04/R05 | Cells / totals matching | Confidence | Discrepancy explanation |
|---|---|---|---|---|---|---|---|
| Total Route Mileage | INFERRED | (UG trench + aerial strand route-footage labels CX1-FTG-N2) / 5280, split by Non-Grant polygons | 14.97 / 18.96 / 16.54 / 24.8 | 14.97 / 18.96 / 18.3 / 24.8 | 0/8 cells, 3/4 totals | Medium | Reference row 6 is typed-in. Network totals for NMK-R02 (14.965 mi), R03 (18.96) and R05 (24.80) equal the sum of route-footage labels (79,017 / 100,133 / 130,955 ft) within rounding. Grant/Non-Grant split differs: the reference split cannot be reproduced f... |
| Aerial Footage | INFERRED | sum of CX1-FTG-N2 FTG labels on RTE_AESTRAND | 0 / 0 / 5,740 / 0 | 0 / 0 / 5,279 / 0 | 7/8 cells, 3/4 totals | Medium | Reference 5,740 ft. Drawing aerial-strand labels in the OTN transport corridor total 5,279 ft (all booked to R04). 461 ft unexplained (risers are 4 x 25 ft = 100 ft). |
| UG Footage | INFERRED | sum of CX1-FTG-N2 FTG labels on RTE_UGTRENCH (fiber-bearing route) | 78,606 / 87,569 / 84,127 / 103,707 | 79,017 / 100,133 / 91,332 / 130,955 | 0/8 cells, 0/4 totals | Medium | CalcFTG.lsp sums CX1-FTG-N2 FTG labels (layers RTE_UGTRENCH / GRANT FTG / NON-GRANT FTG) inside a selected closed boundary, using a window polygon (whole label inside). The tool does the same with the OLM boundary and the Non-Grant polygons. The delivered d... |
| Total Drop Footage | VERIFIED | FX_DROPS drop lines (RTE_SpatialNet_UGDROP, ped edge to address PED, CX1-FTG-N2 length). Area = served address. Reference convention: Non-Grant column = Non-Grant drops ('total ... | 54,157 / 52,678 / 44,359 / 37,197 | – / 52,752 / – / 28,747 | 4/8 cells, 0/4 totals | High | FX_DROPS drop lines: NMK-R03 Non-Grant 52,752 vs reference 52,678 (0.14%). Reference row = 'total - grant' (Non-Grant only). R02/R04 have no drop lines in the combined drawing (FXAUTO not run / not saved), so they are blank and flagged. R05 differs by the s... |
| Residential Count | VERIFIED | sum HC of CX1-COUNT (minus MDU units); grant = FMRESADD2 on GRANTADDRESS layer; cross-checked with address list | 227 / 230 / 209 / 178 | 227 / 230 / 209 / 178 | 8/8 cells, 4/4 totals | High | none |
| Commercial Count | VERIFIED | sum CC of CX1-COMCNT (+unused MDUC) minus MDU commercial units; grant = FMCOMADD2 outside Non-Grant polygons | 2 / 12 / 3 / 7 | 2 / 12 / 3 / 7 | 8/8 cells, 4/4 totals | High | none |
| MDU Count | VERIFIED | FMMULTIADD RESIDENTIAL_COUNT + COMMERCIAL_COUNT by area | 0 / 4 / 4 / 4 | 0 / 4 / 4 / 4 | 8/8 cells, 4/4 totals | High | none |
| CBP-Z14SS0720002BK | VERIFIED | 1 Z-14 housing per ground-mounted OLM; design standard: OLM items always in Grant unless the OLM area has no grant passings | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| CBP-MAX10DSM24 | VERIFIED_TOTAL | count of CX1-MAX10 blocks by location (Non-Grant polygons) | 59 / 51 / 80 / 70 | 59 / 51 / 80 / 70 | 6/8 cells, 4/4 totals | High (totals) / Medium (split) | Network total matches (51). One MAX10 is classified Grant by the current Non-Grant polygons but Non-Grant in the reference - ped near a polygon edge. |
| CBP-MAX5DSM24 | VERIFIED_TOTAL | count of CX1-MAX5 blocks by location (Non-Grant polygons) | 147 / 183 / 136 / 127 | 147 / 183 / 136 / 127 | 0/8 cells, 4/4 totals | High (totals) / Medium (split) | Network totals match exactly in all four networks. Grant/Non-Grant split differs by 2-3 peds in R02-R04 and 8 in R05: peds near Non-Grant polygon edges; R05 also shows larger Non-Grant extents in the reference (vault, 450B, cable and route all shift the sam... |
| CBP-GFP103160002874 | NOT_DETECTED | no GOAT ped symbol defined in the drawing conventions; reference 0 | 0 / 0 / 0 / 0 | – / – / – / – | 8/8 cells, 4/4 totals | n/a | none |
| CBP-GFP083160002873 | NOT_DETECTED | no GOAT ped symbol defined in the drawing conventions; reference 0 | 0 / 0 / 0 / 0 | – / – / – / – | 8/8 cells, 4/4 totals | n/a | none |
| FE0-MAX10EXP4 | INFERRED | MAX peds stock 4 ports, +4 per kit: one kit per 4 passings above 4 fed by a ped (HC + CC within 30/50 ft, as FX_DROPS). In NMK and DMI no ped feeds more than 4, so 0. Reference/... | 0 / 44 / 63 / 0 | 0 / 0 / 0 / 0 | 6/8 cells, 2/4 totals | Medium | MAX peds stock 4 ports (template note 'M Peds Stock 4 upgrade to 8'). No MAX ped in NMK or DMI feeds more than 2 passings (CX1-COUNT/CX1-COMCNT), so no upgrade is needed. Reference = every MAX10 in R03 Grant and R04 Grant only; the new template defaults I23... |
| CBV-HGIB2436 | VERIFIED | count of CX1-VAULT blocks (transport-corridor vaults go to the nearest network) | 2 / 3 / 5 / 9 | 2 / 3 / 5 / 9 | 6/8 cells, 4/4 totals | High | Network total matches (9). Reference books one vault as Non-Grant; it lies inside Grant per current polygons (same R05 boundary pattern). |
| CBP-02049030 | NOT_DETECTED | no ped-with-tap symbol in drawing; reference 0 | 0 / 0 / 0 / 0 | – / – / – / – | 8/8 cells, 4/4 totals | n/a | none |
| CBP-02049031 | NOT_DETECTED | no ped-with-tap symbol in drawing; reference 0 | 0 / 0 / 0 / 0 | – / – / – / – | 8/8 cells, 4/4 totals | n/a | none |
| FE0-07264810 | INFERRED | blank-template note (L27): one ground wire kit per splice location named ...G, first in line after the OLM hub, name ending in 0, or end of line (union, counted once). Policy gr... | – / – / – / – | 70 / 85 / 87 / 79 | 0/8 cells, 0/4 totals | Medium | Blank template (NewPeds 1.27.26, L27) instructs a hand count of grounds: splices with G at the end, first in line, names ending in 0, and EOL peds. The tool counts that union once per splice location (NMK 321: R02 70, R03 85, R04 87, R05 79; DMI 126). The C... |
| FFS-ZMDUL61000SP | NOT_DETECTED | plenum lateral cable not present in drawing conventions; reference 0 | – / – / – / – | – / – / – / – | 8/8 cells, 4/4 totals | n/a | none |
| FFA-F902402G5B | VERIFIED_TOTAL | sum of fiberinfo TOTAL (route FTG + slack SLK) for FC024 segments; Grant/Non-Grant by routed spans; plus splice-report-only cables | 45,490 / 48,019 / 29,399 / 60,067 | 45,490 / 48,019 / 34,686 / 60,167 | 0/8 cells, 2/4 totals | High (totals) / Medium (split) | Network totals = sum of cable-label TOTAL (route + slack) + 100 ft OLM tail from splice reports. Grant/Non-Grant split follows routed spans; reference split differs by a few spans near boundaries. / Drawing cable labels AND splice reports both give FC024 = ... |
| FFA-F904804M6B | VERIFIED_TOTAL | as FC024 for FC048 | 8,471 / 33,245 / 20,472 / 12,994 | 8,471 / 33,245 / 15,285 / 12,994 | 6/8 cells, 3/4 totals | High (totals) / Medium (split) | See FC024 NMK-R04: reference FC048 is 5,187 ft higher than the drawing labels and splice reports. |
| FFA-F907206COB | VERIFIED_TOTAL | as FC024 for FC072 (includes OTN transport cable) | 0 / 6,505 / 19,143 / 7,859 | 0 / 6,505 / 19,143 / 7,859 | 8/8 cells, 4/4 totals | High (totals) / Medium (split) | none |
| FFA-F909608E7B | VERIFIED_TOTAL | as FC024 for FC096 | 10,616 / 5,364 / 0 / 8,507 | 10,616 / 5,364 / 0 / 8,507 | 4/8 cells, 4/4 totals | High (totals) / Medium (split) | Network totals match. Split: reference puts 1,872 ft of R02 FC096 in Non-Grant; routed spans give 1,009 ft - spans near the boundary. |
| FFA-CMSCPED120LA8WF12NS | VERIFIED_TOTAL | as FC024 for FC120 | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High (totals) / Medium (split) | none |
| FFA-CMSCPD144LA8WF12NS | VERIFIED_TOTAL | as FC024 for FC144 | 11,965 / 6,983 / 20,853 / 14,280 | 11,965 / 6,983 / 20,853 / 14,280 | 8/8 cells, 4/4 totals | High (totals) / Medium (split) | none |
| FFA-D168LA8WF12NS | VERIFIED_TOTAL | as FC024 for FC168 | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High (totals) / Medium (split) | none |
| FFA-D216LA8WF12NS | VERIFIED_TOTAL | as FC024 for FC216 | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High (totals) / Medium (split) | none |
| FFA-F92882447B | VERIFIED_TOTAL | as FC024 for FC288 | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High (totals) / Medium (split) | none |
| FE0-FOSC450A66NT0B3V | VERIFIED | splice reports with Enclosure Type FOSC 450A | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High | none |
| FE0-FOSC450B66NT0B3V | VERIFIED | splice reports with Enclosure Type FOSC 450B, area by splice location | 0 / 1 / 1 / 3 | 0 / 1 / 1 / 3 | 6/8 cells, 4/4 totals | High | Network total matches (3). Reference books one 450B as Non-Grant; NMK-05131 sits 23 ft from a Non-Grant polygon edge. |
| FE0-FOSC450C66NT0B3V | VERIFIED | splice reports with Enclosure Type FOSC 450C | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High | none |
| FE0-FOSC450D66NT0T3V | VERIFIED | splice reports with Enclosure Type FOSC 450D, area by splice location | 2 / 2 / 2 / 4 | 2 / 2 / 2 / 4 | 8/8 cells, 4/4 totals | High | none |
| FE0-R863927 | INFERRED | design standard: trays per 450B location = ROUNDUP(fusion splices/24); packages (2 trays) = ROUNDUP(sum of trays/2) per column - spare tray reused at another location | – / 1 / 1 / 2 | 0 / 1 / 1 / 2 | 6/8 cells, 4/4 totals | Medium | design standard with pooled packages: R03 1, R04 1, R05 3 trays -> 2 packages (exact network totals). R05 cell split differs only because NMK-05131 is 23 ft from a Non-Grant edge. |
| FE0-R579575 | INFERRED | design standard: trays per 450D location = ROUNDUP(fusion splices/48) (NMK-02001G 242 -> 6); packages (2 trays) = ROUNDUP(sum of trays/2) per column | 4 / 4 / 4 / 5 | 4 / 5 / 4 / 5 | 7/8 cells, 3/4 totals | Medium | design standard: trays per location ROUNDUP(splices/48), 2-tray packages pooled per column. R02 7 trays -> 4, R04 7 -> 4, R05 9 -> 5 (all exact). R03: 03001G 255 -> 6 + 03004 100 -> 3 = 9 trays -> 5 vs reference 4; the reference appears to have counted 03004 as <=... |
| FE0-R89279 | VERIFIED | 0 - the FOSC450-D6-6-NT-0-T3V closure ships with its tall slack basket ('T' in the part code, CommScope ordering guide); the approved BOM orders 0 | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High | none |
| FM0-FF11002 | SUGGESTED | design standard: burns & heat shrink are not updated in the BOM; audit shows fusion splices only | – / – / – / – | 571 / 699 / 633 / 574 | 0/8 cells, 0/4 totals | Low | design standard: burns & heat shrink are not updated in the BOM. Audit shows fusion-splice count only. |
| IHM-04584865 | VERIFIED | 1 MDU enclosure per FMMULTIADD building | – / 1 / 1 / 1 | 0 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| FM0-3HG01676AB | VERIFIED | 1 SF-8M bundle per CX1_OLM block | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| FM0-3FE47548AD | VERIFIED | design standard: ROUNDUP(Jumper Calculator splitters required / 2) per column = ROUNDUP(ROUNDUP(passings/32)/2) | 5 / 5 / 4 / 4 | 5 / 5 / 4 / 4 | 8/8 cells, 4/4 totals | High | design standard: SFP = ROUNDUP(Jumper Calculator 'Splitters Required' / 2) per column, regardless of the splitter actually designed. |
| FE0-F1PLC32 | VERIFIED | used when the design's PLC couplers are 1x32: network = ROUNDUP(passings/32), Grant = ROUNDUP(grant passings/32) | – / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | High | none |
| FE0-F1PLC64 | VERIFIED | network = ROUNDUP(passings/64) (= splice-report PLC COUPLER 64 rows = address-list PONs); Grant = ROUNDUP(grant passings/64), Non-Grant = remainder | 4 / 4 / 4 / 3 | 4 / 4 / 4 / 3 | 8/8 cells, 4/4 totals | High | none |
| CP0-XM31L903HP120H2SFPAPPS | VERIFIED | 1 power supply per OLM | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| CP0-PWE312020BCKHDSPIRF | INFERRED | 1 pole-mount enclosure per aerial OLM (OLM within 15 ft of an aerial pole) | 0 / – / – / – | 0 / 0 / 0 / 0 | 8/8 cells, 4/4 totals | Medium | none |
| CP0-UPE3UMB12020BTBISABCKSPIR | VERIFIED | 1 ground-mount enclosure per ground OLM | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| CP0-AXM2PS2ECRPEDSUPPO | VERIFIED | 1 precast pedestal support per ground OLM | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| CP0-7460002030001 | VERIFIED | 1 battery cable kit per OLM | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 8/8 cells, 4/4 totals | High | none |
| CPB-195XTV | VERIFIED | 3 batteries per OLM power enclosure (3-battery enclosure) | 3 / 3 / 3 / 3 | 3 / 3 / 3 / 3 | 8/8 cells, 4/4 totals | High | none |

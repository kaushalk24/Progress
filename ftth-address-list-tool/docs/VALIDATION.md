# Validation against the completed reference packs

Two completed packs were used. Client data is not stored in this repository; generated
workbooks, row-level comparisons and exception reports were delivered separately.

* **Region A** – 4 OLMs, 236 closure splice reports (233 system exports + 3 hand-made
  guides), 4 manually prepared address lists (1,384 rows), one combined design DWG.
* **Region B** – 1 OLM, 68 closure splice reports, 1 manual address list (316 rows), one
  design DWG. Region B arrived after the tool was built and was first run by the user
  unchanged; its differences drove the second round of fixes (below).

## Protocol

* Rules were developed on **R02 and R03** only.
* **R04** was the first validation set. It exposed two generic defects (segment
  renumbering between report revisions; street renamed between revisions), which were
  fixed generically, so R04 is partly development data.
* **R05 was held out**: its blind run was recorded before any R05 comparison (only its
  header row and a few MDU rows had been seen during the initial inventory). Afterwards
  R05 exposed three cases that were *flagged* incorrectly as confirmed; the fixes change
  statuses only, never values. No R05 value was used to set a rule.
* Completed-list values are never read when generating; the comparison is a separate step.
* Final figures below are from one run over all 236 reports (cables cross OLM areas, so
  reports filed under another OLM add evidence).

## Region B: discrepancy analysis of the first run, and fixes

The user's run of the released tool (reports only) against the manual list: all 316 rows
matched and PON NAME, PON PORT, FIBER #, ADDRESS, both colours and CABLE NAME agreed
316/316. Differences:

| Field | Rows | Root cause | Fix (generic, configurable) | After |
|---|---|---|---|---|
| Fiber Splice blank, manual has a closure | 67 | Reports of the tap-splice closures not in the pack | Design-drawing resolution `FS-DRAWING` (built-in DWG object decoder, see FIELD_MAPPING) | 67/67 equal |
| Fiber Splice blank (`CIRCUIT_CONFLICT` error) | 1 | **Bug**: downstream records named another house number (digits swapped) on the same circuit; the trace stopped | Same circuit = live record whose circuit start/end is the hub; trace continues, address flagged `ADDR-VARIANT` (drawing has an address point only for the hub's number) | equal |
| Fiber Splice = cable end, manual = earlier closure | 1 | **Bug**: a cut piece with state `Residential` and the same usage text was bridged as if live | Cut pieces recognised by their circuit ends (two closures, not the hub) and used as break-point evidence | equal |
| Fiber Splice = hub, manual blank | 4 | Manual convention: hub-ending fibres show the hub only on the feeder and the first distribution section (60 of 60 rows in 5 lists) | `fiber_splice.hub_value_sections` | 4/4 equal |
| Fiber Tap Name | 2 | Manual typo: trailing `:` after the tap name | none (reports are right) | unchanged, reported |

Also found and now flagged (values kept as recorded): 4 addresses without a house number
(`ADDR-NO-NUMBER`, PROVISIONAL), 29 addresses with a repeated word such as `AVE AVE`
(warning), and one hub/downstream premise disagreement (`ADDR-VARIANT`).

Region B after the fixes, with the drawing: **every field 316/316 except Fiber Tap Name
314/316 (the manual typo); Fiber Splice 316/316**; 0 UNRESOLVED rows. All 68 `FS-DRAWING`
values equal the manual list; the drawing corroborated all 128 other report-derived values.

## Region A: coverage and accuracy (4 OLMs, 1,384 rows)

Row matching on OLM + cable + fibre: **1,384 / 1,384 rows matched both ways**, no
duplicates, **row order identical** in all four lists, same sections in the same order.

| Field | Exact match | After whitespace/case normalisation | Notes |
|---|---|---|---|
| PON NAME | 1,384 / 1,384 | – | 884 populated values, all equal |
| PON PORT | 1,384 / 1,384 | – | |
| FIBER # | 1,384 / 1,384 | – | |
| CABLE NAME | 1,384 / 1,384 | – | |
| COLOR FIBER | 1,384 / 1,384 | – | |
| COLOR TUBE | 1,312 / 1,384 | 1,312 | 72 differences = manual error (tubes 3–8 of one 96-fibre cable entered as BL/OR repeatedly); tool values equal the report colours and the colour-code sequence |
| Fiber Tap Name | 980 / 1,384 | **1,384 / 1,384** | 404 differences are leading spaces in two manual lists |
| ADDRESS | 1,316 / 1,384 | 1,367 / 1,384 | 17 substantive: 15 manual errors (5 missing leading digit, 3 dropped "C-" prefix, 1 with both, 6 transport FORWARD fibres labelled RETURN) and 2 source conflicts that the tool flags PROVISIONAL |
| Fiber Splice | **1,381 / 1,384** | 1,381 | with the drawing; see below |

**Fiber Splice** (denominator matters). The manual has a value in 931 rows.

| Run | Rows with a value | Equal to manual | UNRESOLVED rows |
|---|---|---|---|
| First release, reports only | 635 of 931 (68 %) | 631 of 651 values | 296 |
| Fixed tracer, reports only | 646 of 931 (69 %) | 642 of 646 values | 285 |
| Fixed tracer + drawing | **931 of 931 (100 %)** | **928 of 931 (99.7 %)** | **0** |

By rule (with the drawing): `FS-HUB` 47/47, `FS-TRACE-TERMINAL` 71/71, `FS-CABLE-END`
242/243, `FS-BREAK-POINT` 243/245, `FS-DRAWING` 286/286, `FS-SEG-ALIAS` 23/23, `FS-GUIDE`
13/13, `FS-TAP-CABLE` 3/3 equal. The 3 remaining differences:

* 1 manual typo in the closure prefix;
* 2 report-derived values (one cable end, one break point) where the manual names another
  closure. In both, the drawing supports the tool's closure (drop symbol from the premise to
  that closure's tap enclosure) and nothing in the reports or the drawing supports the
  manual's closure (no drop symbol towards it; 365 ft from the premise in one case). They
  stay PROVISIONAL with the evidence and are listed for review.

One more report-derived break point pointed at a closure without a tap enclosure; the
drawing found the branch closure beyond it, which equals the manual (rule `FS-DRAWING`).

Row status of the generated lists with the drawing: region A **571 CONFIRMED (41 %),
813 PROVISIONAL (59 %), 0 UNRESOLVED**; region B **119 CONFIRMED, 197 PROVISIONAL,
0 UNRESOLVED**. All workbooks are DRAFT until the provisional rules are accepted or
reviewed (README, *Review and approval workflow*).

Holdout R05, blind run (before the R04-driven fixes and before combining all reports):
rows 268/268 matched, order identical, PON/fibre/colour/cable 100 %, tap 100 %
normalised, address 264/268 normalised, Fiber Splice 199/268 exact. Final: Fiber Splice 267/268.

## Root causes of the remaining differences (both regions; none unexplained)

| Class | Count | Owner |
|---|---|---|
| Manual tube-colour sequence error | 72 | reference list (A) |
| Leading spaces in manual cells | 455 | reference list (A, cosmetic) |
| Manual address typos (missing digit, dropped prefix) | 9 | reference list (A) |
| Manual transport label contradicts report | 6 | reference list (A) |
| Manual closure-id typo | 1 | reference list (A) |
| Manual trailing colon after tap name | 2 | reference list (B) |
| Source data conflict between report revisions / bad usage text | 2 | spatial system (A, flagged) |
| Manual Fiber Splice not supported by reports or drawing | 2 | review (A) |

## Source-data issues found (all reported in the Exceptions sheets)

* Hub reports of three OLMs exported three weeks after the downstream reports; between
  the revisions a street was renamed, a tap changed house number, a building suffix
  changed, and one cable's segments were renumbered (handled: `SEGMENT_NUMBER_MISMATCH`,
  `USAGE_TEXT_VARIANT`, `DOWNSTREAM_CIRCUIT_DIFFERS`).
* One usage record has the tap id where the address belongs (`ADDRESS_SUSPECT`).
* Usage tap prefix differs from the circuit's terminal enclosure on 6 fibres (`TAP_CONFLICT`).
* Duplicate address on two fibres (`DUPLICATE_ADDRESS`).
* Three hand-made splice guides with internally inconsistent colours (`GUIDE_DUPLICATE_FIBER`).
* 88 % of the closures named in the reference Fiber Splice column (624 of 706) have no report (*Reports to Request*).
* Region B: hub and downstream reports name different house numbers on one circuit
  (`DOWNSTREAM_PREMISE_DIFFERS`); 4 usage addresses have no house number, 29 repeat a word.

## Drawing

Both DWGs (AC1032) were read by the built-in object decoder with 0 decode errors (region A
70,399 objects, region B 43,189). Region A: 867 closures, 705 tap enclosures with pigtail,
875 address points, 874 drop symbols; region B: 231, 182, 224 and 223. Address-point
coverage (house number + street core): region A 861 of 868 drawn points are served by the
lists, region B 209 of 212; the unserved points are listed for review. Every hub and every
generated Fiber Splice closure exists in the drawing.

## Failure cases tested (tests/)

Missing/empty folders, no hub report, missing report column, corrupt workbook, duplicate
report, duplicate address and reused PON port, tap conflict, incomplete connectivity,
conflicting circuit downstream, segment renumbering between reports, invalid config,
overrides (set, accept, stale, unapproved), never-overwrite, DRAFT vs FINAL naming,
leading zeros kept as text, DXF cross-check and address coverage, unsupported/missing/
corrupt drawings; cut piece with the same usage text, same-circuit premise variant,
transport convention, tap's own cable, address quality flags; DWG bit codes and handle
map; design model, drawing resolution (fill, corroborate, branch beyond a closure without
enclosure, no candidate, rule policy, end-to-end); assignment vs brute force, fibre-order
learning; and an opt-in reference-pack test (`FTTH_REFERENCE_PACK`, also checks the
drawing resolution: no UNRESOLVED row and >= 99 % Fiber Splice agreement). Both packs pass it.

## Known limitations

* Fiber Splice is CONFIRMED only with the report of the tap-splice closure; drawing and
  report inferences stay PROVISIONAL until reviewed or accepted by policy.
* Drawing resolution needs the drawn network to match the reports' revision; a drawing
  of another revision can mislead it (the corroboration counts in the run summary show it).
* The fibre-order convention is learned per run; with fewer than 10 traced pairs, or less
  than 90 % agreement, it is not used.
* DWG decoding is verified on AC1032; AC1024/AC1027 are attempted (same layout), older
  versions need a DXF.
* Colour codes beyond 12 tubes repeat the 12-colour sequence (stripes/dashes not modelled).
* Splitters must follow the `PLC COUPLER <ratio> <index>` naming (configurable regex).
* Grant/non-grant areas exist in the drawing but are not part of the address-list layout;
  the tool does not filter on them.

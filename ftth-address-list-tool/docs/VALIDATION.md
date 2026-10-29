# Validation against the completed reference pack

Reference pack: one region, 4 OLMs (R02–R05), 236 closure splice reports (233 system
exports + 3 hand-made guides), 4 manually prepared address lists (1,384 rows), one
combined design DWG. Client data is not stored in this repository; the generated
workbooks, the row-level comparison and the exception reports were delivered separately.

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

## Coverage and accuracy (all 4 OLMs, 1,384 rows)

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
| Fiber Splice | 1,068 / 1,384 | 1,068 | see below |

**Fiber Splice** (denominator matters):

* Reference has a value in 931 rows; the tool produced a value in 635 of them (**68 %
  coverage**). The other 296 rows are UNRESOLVED (blank) because the closure reports
  that would locate the splice were not supplied.
* Of the 651 values the tool produced, **631 equal the reference (96.9 %)**. The 20 others:
  16 transport fibres where the reference leaves the cell blank on some cables but not
  others (inconsistent manual convention; the tool gives the hub), 1 mistyped closure
  prefix in the reference, and 3 provisional inferences that disagree with the
  reference (in one the splice reports explicitly show a different path from the
  reference; two are break-point inferences where a branch splice is possible).
* By status: CONFIRMED 134 values (118 equal; the 16 transport rows above), PROVISIONAL
  517 values (513 equal). The provisional rules (cable end, break point) are therefore
  reliable on this pack, but they are still inferences and stay PROVISIONAL unless the
  engineering lead accepts them.

Row status of the generated lists: **571 CONFIRMED (41 %), 517 PROVISIONAL (37 %), 296
UNRESOLVED (21 %)**. Every non-confirmed row is non-confirmed because of Fiber Splice;
only 12 of them also carry an address/tap flag. All four workbooks are therefore DRAFT.

Holdout R05, blind run (before the R04-driven fixes and before combining all reports):
rows 268/268 matched, order identical, PON/fibre/colour/cable 100 %, tap 100 %
normalised, address 264/268 normalised, Fiber Splice 199/268 exact. Final: Fiber Splice 213/268.

## Root causes of differences (every difference classified; none unexplained)

| Class | Count | Owner |
|---|---|---|
| Manual tube-colour sequence error | 72 | reference list |
| Leading spaces in manual cells | 455 | reference list (cosmetic) |
| Manual address typos (missing digit, dropped prefix) | 9 | reference list |
| Manual transport label contradicts report | 6 | reference list |
| Manual Fiber Splice blank for transport fibres on some cables | 16 | reference list (inconsistent convention) |
| Manual closure-id typo | 1 | reference list |
| Source data conflict between report revisions / bad usage text | 2 | spatial system (flagged) |
| Provisional inference differs from manual | 3 | review |
| Unresolved – closure reports missing | 296 | data request |

## Source-data issues found (all reported in the Exceptions sheets)

* Hub reports of three OLMs exported three weeks after the downstream reports; between
  the revisions a street was renamed, a tap changed house number, a building suffix
  changed, and one cable's segments were renumbered (handled: `SEGMENT_NUMBER_MISMATCH`,
  `USAGE_TEXT_VARIANT`, `DOWNSTREAM_CIRCUIT_DIFFERS`).
* One usage record has the tap id where the address belongs (`ADDRESS_SUSPECT`).
* Usage tap prefix differs from the circuit's terminal enclosure on 6 fibres (`TAP_CONFLICT`).
* Duplicate address on two fibres (`DUPLICATE_ADDRESS`).
* Three hand-made splice guides with internally inconsistent colours (`GUIDE_DUPLICATE_FIBER`).
* 88 % of the closures named in the reference Fiber Splice column (624 of 706) have no report (`SPLICE_CLOSURE_UNKNOWN`, *Reports to Request*).

## Drawing cross-check

Built-in DWG string scan (no converter available): every hub and every Fiber Splice
closure the tool generated was found in the drawing; all 236 report closures, all 670
closures named in segment tables and 705/706 closures in the reference lists were found
(the missing one is the reference typo). 267/352 cable names were found. No tap names,
fibre, port or splitter data exist as drawing text. The DXF path (full attribute read,
address-point coverage) is implemented and unit-tested but was not run on this drawing.

## Failure cases tested (tests/)

Missing/empty folders, no hub report, missing report column, corrupt workbook, duplicate
report, duplicate address and reused PON port, tap conflict, incomplete connectivity,
conflicting circuit downstream, segment renumbering between reports, invalid config,
overrides (set, accept, stale, unapproved), never-overwrite, DRAFT vs FINAL naming,
leading zeros kept as text, DXF cross-check and address coverage, unsupported/missing/
corrupt drawings, and an opt-in reference-pack test (`FTTH_REFERENCE_PACK`).

## Known limitations

* Fiber Splice cannot be confirmed without the report of the tap-splice closure.
* Break-point inference marks where a fibre leaves a cable; that can be a branch splice.
* The built-in DWG reader recovers text only (no geometry, no tag–value pairing); use DXF.
* Address-point coverage needs DXF block attributes (or a premise export); Map 3D object
  data is not part of DXF.
* Colour codes beyond 12 tubes repeat the 12-colour sequence (stripes/dashes not modelled).
* Splitters must follow the `PLC COUPLER <ratio> <index>` naming (configurable regex).
* Grant/non-grant areas exist in the drawing but are not part of the address-list layout;
  the tool does not filter on them.

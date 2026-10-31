# Research recovery checkpoint

This file lets work resume after a usage-limit interruption with no loss. Update it after every meaningful discovery, code change or test run.

_Last checkpoint: 2026-10-31 ~08:20 UTC. **The 0.5.0 task is complete.** Code is in `a4e4a6d`, plus a docs commit. 77 of 77 tests pass, including the slow end-to-end test. The deliverables are in `$S/out5` (NMK_ref, NMK_new, DMI), and every job exited 0 with workbook FAIL=0 and deep-check ERROR=0._

## 1. Task being resumed

"Deep technical research, forensic BOM reverse engineering and FTTX automation improvement", started on top of build 0.4.0 (commit `1342c5c`). Deliverables A–G:

- **A.** Per-item findings: original quantity, reconstructed formula, evidence, calculated value, discrepancy, confidence.
- **B.** Verified rules catalogue.
- **C.** Technical research with references.
- **D.** Improved code.
- **E.** Debugging evidence.
- **F.** Regenerated NMK reconciliation and DMI-R15 BOM.
- **G.** Critical unresolved issues.

## 2. Last confirmed working application state

- Branch `claude/cool-hawking-1eddej`, HEAD `1342c5c` (0.4.0), pushed. The working tree was clean when this session resumed.
- 0.4.0 test result: `python -m pytest -q` gave 43 passed (with `FTTX_TEST_DATA` set to the scratch inputs).
- NMK reconciliation: 292 of 360 area cells match, and 156 of 180 network totals match.
- Test data, which is client data and is never committed: `$S/inputs`, where `S=/tmp/claude-0/-home-user-Progress/4269fd75-4314-5e21-8b90-ae6bb189e9e4/scratchpad`. It holds `dwg/`, `addr/`, `splice/`, `bom/` (approved NMK BOM), `dmi/` and `template2/` (the new blank template).

## 3. Agents

| Agent | Assignment | Status | Saved findings | Next action |
|---|---|---|---|---|
| `a571c50da484b9a65` (research) | External sources: FOSC 450 trays, RaDD MAX5/MAX10, Nokia SF-8M, slack/storage practice, BEAD cost allocation, LibreDWG/ezdxf limits | **Done** (resumed with SendMessage, then handed back) | `$S/research/external_findings.md` (345 lines; URL and category per claim), `$S/dl1/sel.pdf`, `$S/gh/*` | Curate into RESEARCH.md (deliverable C) |
| `a9eed886c686e5720` (code review) | Independent, skeptical review of the package (read-only) | **Done**: 19 findings, all handled (see section 9) | `/tmp/claude-0/review_scratch/code_review.md` (written as it goes) | Verify each finding, fix it with a regression test |

### Network constraint found by the research agent

The environment's network policy blocks most vendor and government hosts with DNS failures: commscope.com, raddnetwork.com, nokia.com, amt.com, ntia.gov, ecfr.gov, autodesk.com, corning.com and lightwaveonline.com. The hosts that can be reached are github.com, raw.githubusercontent.com, s3.amazonaws.com and the package registries. WebSearch works, but most results can't be fetched. Any claim from a blocked source must be marked "search snippet only" or "unverified".

## 4. Verified forensic results so far

The scripts are in `$S/forensic/`. Each takes the package path as `argv[1]`, and `load.py` loads NMK or DMI.

| # | Topic | Result | Evidence | Confidence |
|---|---|---|---|---|
| F1 | Ped type and cable size (f1) | MAX5 is placed on cables of 48F or less. MAX10 is placed on 48–144F cables. The template note "MAX10 above 72F / MAX5 at 48F or less" is broken by 60 NMK and 47 DMI MAX10 peds on 48F or 24F cables. | Count of ped block against the nearest cable fibre count | High |
| F2 | Ped type and topology (f2) | **MAX5 is never at a pass-through on a cable above 48F** (0 in NMK, 0 in DMI). MAX10 is at pass-throughs on cables above 48F (NMK 111, DMI 11) and at most branch splices. A MAX5 at a branch on a cable above 48F occurs 5 times in NMK and once in DMI, all with splice reports. | Ped classified as pass / branch / end against the routed cables | High: a design check, not a BOM quantity |
| F3 | Ground wire kit (f3) | The template-note union (G suffix, OR name ends in 0, OR first splice after the hub, OR end of line) gives 319 NMK locations: R02 71, R03 83, R04 86, R05 79. G suffix and end of line agree for 243 of 248. The DMI run crashed because the OLM name "DMI-R15" was counted as a "first in line" splice name; the fix is to keep only real splice names. | f3 output | Medium: the rule comes from the template note; the reference row is blank |
| F4 | Cable Grant split (f4) | H1 (span majority, the current engine) gives the lowest error: 2,497 ft absolute Non-Grant error over 12 cells, 8 exact. H7 equals H1. H2 (length inside the polygon) gives 4,126. H3 to H6 range from 5,203 to 66,617. H8 (address/BEAD allocation of passings carried) gives 86,323 and is **rejected**. | f4 output | High |
| F5 | Label geometry (f5) | Route FTG labels sit about 5 ft from the trench polylines; cable polylines are offset about 25 ft. Label FTG against trench length has a median difference near 0, with outliers (one at -881 ft). | f5 output | High |
| F6 | Route Grant split (f6) | Splitting by label point, by a window along the path, or by trench length all fail to reproduce the reference. R02 is within about 1,000 ft. R05 is about 21,600 ft off in the same direction on every method, which points to the Non-Grant boundary changing after the manual BOM. Matching labels to polylines is ambiguous (95 labels with no trench match, 158 polylines with more than one label), so a stale-label check gives too many false positives to ship. | f6 output | High that the split can't be reproduced; the cause is inferred |

### Research results that bear on BOM rules (from the agent's log)

- **FOSC 450 tray kits** (CommScope/Tyco ordering guide, opened from S3; the guide is the 2004 edition): FOSC-ACC-B-TRAY-24 (863927-000) and FOSC-ACC-D-TRAY-48 (579575-000) each have SOQ 2 and contain 2 trays. A B tray holds 24 single-fusion splices and a D tray 48. This confirms the tray rule: one package = 2 trays = 48 splices (B) or 96 splices (D).
- **FOSC450 closure codes:** NT means no trays and 0 means none pre-installed, so trays are always ordered separately. B6 takes up to 6 B trays. The T basket takes 5 trays and the D6 8. "3" means 3 ground lugs; "V" means valved.
- **Other topics:** there are no public RaDD MAX5/MAX10 specs (blocked), and no NTIA-prescribed split method. Slack values are project parameters. LibreDWG skips some R2010+ objects without warning, so its read status must be surfaced, which the tool already does.

## 5. Unresolved hypotheses

- Route footage definition (rows 6–10): the reference uses a different method in each network. Not reproducible; needs an SME decision. The tool computes both options as policies.
- MAX10 +4 upgrades: the reference gives 44/63 as a blanket rule; need-based gives 0. Policy options exist.
- R04 FC024 to FC048: a 5,187 ft move in the reference that both the drawing and the splice reports contradict. Treated as a reference error.
- The R05 Non-Grant boundary probably changed after the reference BOM.

## 6b. State at the 07:55 checkpoint

- **Implemented beyond the earlier plan:**
  - rule FE0-R89279 D basket = 0 (T3V includes the tall basket; the reference is 0);
  - CLOSURE_OVER_CAPACITY check;
  - the discrepancy report's mileage tolerance (0.5 mi hid differences; now 0.01 mi, as in calibration);
  - version 0.5.0;
  - CHANGELOG, README, BOM_RULES (chains) and RESEARCH.md written.
- **Verification done:**
  - every takeoff quantity was compared between 0.4.0 (a git worktree at `$S/wt040`) and 0.5.0, on NMK and on DMI;
  - the only changes are `grounding_points` and `basket_d`;
  - the reviewer's experiment scripts were rerun after the fixes (`/tmp/claude-0/review_scratch/rerun_after_fix.txt`) and all show the fixed behaviour.
- **Final results:**

  | Run | Cells | Totals | Deep check |
  |---|---|---|---|
  | NMK, reference template | 298/368 | 160/184 | ERROR 0, WARN 42, INFO 36 |
  | NMK, new template, one BOM per OLM | R02 77/92, R03 73/92, R04 75/92, R05 73/92 (sums to the combined run) | 42+40+37+41 = 160/184 | ERROR 0 |
  | DMI-R15 | (no reference) | | ERROR 0, WARN 17, INFO 26 |

- **Late fix:** each ped-splice is tied to its nearest housing and FOSC-closure splices are excluded. This removed 4 false MAX5 hits (the OLM hub splices). The rule is now "no MAX5 on a cable above 48F, any role".
- **Next actionable tasks (only if the user asks):**
  - SME decisions G1–G4 (PROGRESS_AND_ISSUES.md);
  - allow the vendor hosts in network settings and verify the current CommScope tray limits;
  - check the LibreDWG version bundled in `@mlightcad/libredwg-web@0.8.0`;
  - review finding 18 (scope learned evidence per project).

## 6. Exact unfinished operations at the interruption (original list, items 1–5 now done)

1. ~~Fix the f3 filter and rerun it for DMI~~ **done** in `f3b_ground.py` and `f3d_first.py`:
   - The template note is on blank template L27: "Hand count for Grounds: All splices with letter G at End, First in line, any ending in a zero, and also EOL Peds".
   - The splice symbol sits 20–55 ft from its ped, and the routed cable paths pass exactly through the splice points (0 ft).
   - **First in line** is the first splice point on the routed path of each cable leaving the OLM hub. The hub is the splice nearest the OLM block, 63–132 ft away. This gives 11 in NMK and 3 in DMI (DMI-15002G, DMI-15116G, DMI-15171).
   - **DMI:** G 116, EOL 69 (all of them G), ends-in-0 9. The union is about 126.
   - **Housings:** in NMK, G and EOL are 99% MAX5 peds; in DMI, 47 G are MAX10 or vault.
2. Implement the ground-kit rule in `takeoff.grounding_points` as a `ground_kits` policy (`template_note` as the default, `g_suffix`, `not_ordered`), and update rule FE0-07264810.
3. Add the doctor check `MAX5_ON_LARGE_CABLE`, plus an INFO for MAX10 placed where a MAX5 would do.
4. Add tests and run the full suite.
5. Regenerate the NMK outputs (reference template and new template) and the DMI-R15 outputs.
6. Write the deliverable documents: FORENSIC_FINDINGS.md (A), BOM_RULES.md chains (B), RESEARCH.md (C), PROGRESS_AND_ISSUES.md and CHANGELOG.md for 0.5.0 (G).
7. Commit and push.

## 7. Files changed since 0.4.0 (not yet committed)

- `engine/takeoff.py`:
  - `ground_locations()` and `_first_on_path()`;
  - `grounding_points()` now follows the template-note union, with reasons as evidence and a WARN when no hub is found;
  - `ON_PATH_FT`, `GROUND_HUB_MAX_FT`.
- `engine/policies.py`:
  - new policy `ground_kits` (template_note, g_suffix, not_ordered);
  - `calibrate()` skips rows that are blank in every reference column (missing is not zero);
  - `compute_variants()` no longer crashes when a cable has no base key.
- `engine/doctor.py`: `ped_cable_roles()`, plus checks MAX5_ON_LARGE_CABLE (WARN, any role) and MAX10_SMALL_CABLE (INFO). The splice goes to its nearest housing, and closure splices are excluded.
- `config/bom_rules.json`: FE0-07264810 changed to INFERRED, write=true.
- `config/investigations.json`: FE0-07264810 note.
- `tests/test_forensic_rules.py`: 6 new tests, all passing.

Verified on the real data:
- ground kits: NMK R02 G19/NG51, R03 23/62, R04 21/66, R05 56/23 (total 321); DMI 77/49 (126);
- design checks after the nearest-housing fix: NMK 1 MAX10_SMALL_CABLE, DMI 3; no MAX5_ON_LARGE_CABLE in either. The earlier MAX5 "branch" hits were the OLM hub splices, which sit in FOSC closures.

## 8. Tests completed since 0.4.0

- `tests/test_forensic_rules.py`: 6 passed.
- Full non-slow suite after the ground-kit and design-check changes: 48 passed.
- After review fixes 1–3: 56 passed (11 in `test_forensic_rules.py`, plus 3 new integration tests).

## 9. Code-review findings to fix (from `/tmp/claude-0/review_scratch/code_review.md`)

1. ~~BLOCKER: a single-network job books neighbouring and transport-corridor material~~ **FIXED**.
   - The classifier keeps the other networks' boundaries as `foreign` and records their objects in `foreign_assigned`; they are not counted.
   - The transport network is resolved from the splice naming.
   - Cables belong to their A-end network, and other networks' cables are kept in `tk.foreign_cables` for topology.
   - Splice-report networks are resolved by name, then by drawing location (`resolve_report_networks`).
   - Test `test_single_olm_run_equals_combined_run`: all 4 NMK OLMs give identical cells.
2. ~~BLOCKER: an unrecognised boundary label counts the whole drawing~~ **FIXED**.
   - The whole-drawing fallback applies only when there are no boundary polygons at all, or one unlabelled polygon is used; both give a WARN (NETWORK_BOUNDARY_FALLBACK).
   - Otherwise the note becomes ERROR NETWORK_BOUNDARY.
   - The label regex is now in conventions.json (`network_label_regex`, `splice_name_regex`).
3. ~~MAJOR: KeyError~~ **FIXED**: `Classifier.job` and `in_job()`; there is no region lookup by the transport name.
4. ~~Address-list header and extra sheets~~ **FIXED**: columns are matched by name, other sheets are skipped (noted), and an empty list falls back to the drawing counts.
5. ~~Mixed split ratios~~ **FIXED**: the second ratio is written from its designed count, with a WARN.
6. ~~Enclosure spelling~~ **FIXED**: one shared regex, `non_bom_enclosures`, and a WARN for unknown types.
7. ~~Report network~~ **FIXED**: by name, then by drawing location.
8. ~~Own FINAL_BOM taken as the reference~~ **FIXED**: the output folder is excluded, generated names are skipped, and the workbook keyword `fttx_bom generated` marks our files.

Findings 9–19 from the reviewer's final report:
- **9 FIXED:** `template_capacity` = min(main, Transport, Jumper).
- **10 FIXED:** area columns are located from the Total Quantity header.
- **11a FIXED:** no FOSC lines without splice reports.
- **11b FIXED:** an undefined block gives a blank line and an ERROR.
- **12 DOCUMENTED:** INFO CABLE_CROSS_NETWORK.
- **13 FIXED:** AST-restricted evaluator.
- **14 FIXED:** zip limits, and no merging by stem.
- **15 FIXED:** absolute LibreOffice profile URI.
- **16 FIXED:** tolerant numbers; an unreadable report is skipped with an ERROR.
- **17 FIXED:** the doctor resolves without logging.
- **19 FIXED:** consistent cable rounding.
- **2 (rest) FIXED:** a network with no boundary gets a blank BOM and an ERROR.
- **18 OPEN:** learned-evidence key collisions between projects. MINOR; documented.

Tests: `tests/test_review_regressions.py` (12) plus 4 more integration tests. **72 passed** (non-slow).

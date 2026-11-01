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

- Route footage definition (rows 6–10): the reference uses a different method in each network. Not reproducible; needs a design decision. The tool computes both options as policies.
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
  - design decisions G1–G4 (PROGRESS_AND_ISSUES.md);
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

---

# Task 2 (started 2026-10-31 after 0.5.0): DMI-R15 manual BOM reconciliation

What the user asked for:
1. Do deep research on the manual DMI-R15 BOM, saved at `$S/inputs/dmi_ref/386021_MelcherDallas_BEAD_FTTH_DMI-R15_BOM.xlsx`. Client data: not committed.
2. **RF support structures are not calculated.** DMI-R15 also contains an RF (coax) network, and its structures must be excluded.
3. **The user's Grant/Non-Grant rule:** Non-Grant = everything inside the Non-Grant boundaries; Grant = total − Non-Grant.

Status: started. The steps are to:
1. inspect the reference;
2. run DMI with `--reference`;
3. find the RF structures in the DWG;
4. test the NG-inside / G = total − NG rule on NMK and DMI;
5. implement it, test, regenerate, and commit.

## Task 2 checkpoint (code changes done, not yet committed)

**Findings on the DMI manual BOM** (forensic scripts `$S/forensic/d1`–`d11`):
- **FC024:** the approved BOM double-counts the duplicated label "DMI-14001G TO DMI-15204G" (6,467 ft).
- **Aerial footage 512 ft:** RF strand with no aerial fiber cable. Excluded.
- **Vault 3CC8B7:** an RF vault at the amplifier. Excluded, giving 8 vaults.
- **SFP:** Non-Grant = ROUNDUP(NG/64), Grant = ROUNDUP(total/64) − Non-Grant. This is the user's rule, now the default. It also gives NMK 15 SFP = 15 designed PONs.
- **MAX10 +4:** the template formula (Non-Grant MAX10) is now the default.
- **Ground kits:** blank in both approved BOMs, so the line is no longer written (SUGGESTED).
- **Drops:** the two BOMs disagree. The default is now "both" (Non-Grant inside, Grant = total − Non-Grant), with options nongrant_only and total_nongrant.
- **UG route:** −1.8%; one 2,374 ft trench has no fiber (WARN TRENCH_NO_FIBER, policy fiber_bearing).
- **D trays:** 5 in the approved BOM against 4 from the rule. Unexplained.
- **Bonding jumper and ped bonding kit:** the approved BOM inherits the template's inconsistent column formulas. The tool repairs them.

**Code changes:**
- renamed BOM sheet support (`detect.bom_sheet_name`);
- `takeoff.SegIndex`, `rf_support_test`, and the RF exclusion in `count_blocks` and `route_footage`;
- policy `engine` field; new options and defaults (sfp, max10_upgrade, drop_columns, route_footage);
- conventions: `rf_*`;
- rules, investigations, and doctor checks RF_EXCLUDED and TRENCH_NO_FIBER.

Tests: 76 pass.

## Task 2: latest state

- Code committed and pushed as `2c6d3b9` (0.6.0 code).
- Docs updated: FORENSIC_FINDINGS (DMI section), BOM_RULES (Grant/Non-Grant rule, RF), README, CHANGELOG.
- The deliverable runs are going: `bash $S/regen7.sh`, which writes to `$S/out7`, log `$S/out7.log`.

Remaining:
1. wait for EXIT1–3;
2. update PROGRESS_AND_ISSUES with the numbers;
3. run the slow test;
4. commit and push the docs;
5. send the files.

## Task 2: done

Outputs are in `$S/out7`, and every run passed workbook verification (FAIL=0, recalculated):

| Run | Cells | Totals | Deep-check errors |
|---|---|---|---|
| DMI-R15 against the manual BOM | 75/90 | 38/45 | 0 |
| NMK, reference template | 290/368 | 156/184 | 0 |
| NMK, per OLM (sums to the above) | 75 + 70 + 74 + 71 | 40 + 39 + 37 + 40 | 0 |

88 tests pass, including the slow one.

**Open decisions for the user:**
- the drop-column convention;
- D trays (5 against 4);
- the remaining UG route gap;
- fixing the template's bonding formulas.

---

# Task 3 (started 2026-10-31): professional refinement, new drawing DMF-R04, reference material re-study

What the user asked for:
1. Make the tool simple and professional. **No wording that refers to where the design knowledge came from** in the tool, docs or outputs.
2. Plan and implement a professional UI.
3. Highlight cells without confidence in the extracted BOM.
4. Re-study the design-standard reference material and reverse-engineer it in depth. Correct values matter more than matching a manual BOM, which may contain errors.
5. New drawing `$S/inputs/dmf/386029_South_Des_Moines_FTTH_DMF-R04_DWG.dwg`. It contains existing HFC plant and fiber networks that were not designed by us. Our designs use M5/M10 peds with a bulkhead for the enclosure. Only our design counts.

Assets: the design reference material in the session workspace. The exact paths are in the private recovery log in the scratchpad.

Plan:
- A: design-standard study → scratchpad research notes.
- B: DMF-R04 forensic.
- C: rule fixes.
- D: remove source-reference wording.
- E: confidence highlighting.
- F: UI redesign.
- G: tests, regenerate, commit.

## Task 3 checkpoint 1

- **Design reference:** re-read. A background agent is studying the reference screens and writes its findings to the scratchpad.
- **Rule change from the notes:** SFP is per column, ROUNDUP(splitters/2) (10:47–13:30). Revert the default to jumper_half; total_minus_ng stays an option.
- **DMF-R04: Non-Grant polygons recovered.** They are SNMPOLYGON custom entities that the converter dropped. `tools/dwg2json.mjs` now emits every UNKNOWN_ENT with its preview graphics as ACAD_PROXY_ENTITY. That gives 8 polygons on "Boundary - Designed Not Built", 7 labelled NON GRANT 1–7 and 1 unlabelled. The cache key now includes the converter hash.
- **DMF-R04 networks:**
  - existing HFC: DES_* devices, coax DES_\d+P/T layers, CX1-PED4, poles, anchors, CX1_NODE;
  - other fiber (not ours): CX1_4PT_MST on DES_FIBER_SPL, with splices DMF-04002..04025 at MSTs. Cables FC144 04001→04021, FC072 04001→DMF-P21-A (HFC node) and FC024 04008→04010;
  - ours: MAX5/MAX10 splices DMF-04028..04043G; FC024 04001→04026 (aerial), 04026→04027, 04027→04043G, 04027→04036G and the laterals.
- **Next:** define and implement the "our design" filter (splice housed in an MST or HFC ped means foreign; a cable is foreign when either end is foreign or an HFC node; structures must be on our cable paths).

## Task 3 checkpoint 2 (code not yet committed)

**Design scope** (`takeoff.design_scope`, `exclude`; conventions `foreign_fiber_blocks`, `hfc_*`, `coax_layer_regex`):
- splices at MST terminals are foreign;
- cables ending at a foreign splice or an HFC node are foreign;
- structures must be on our route (within 40 ft) or at our splice (within 50 ft);
- trench along coax with none of our fiber is RF;
- count blocks at HFC/MST/RF-tap plant are excluded;
- without an address list, address blocks count only when their nearest housing is our ped.

**DMF-R04 result:**
- passings 18;
- MAX10 6 / MAX5 10;
- vaults 7, with 1 L-box excluded;
- FC024 27,095 ft (9,217 UG + 17,878 aerial);
- route UG 15,615 / 2,119, aerial 15,671;
- excluded: FC144 1,830, FC072 2,075 (to HFC node), FC024 149 and 27 trench labels; 12 RF trench and 5 RF strand labels.

**NMK/DMI regression check against 0.6.0:** only SFP (back to per-column, as in the reference material) and NMK R04 UG −684 ft (RF trench) changed.

**Next:**
- remove the source-reference wording;
- confidence highlighting;
- UI;
- integrate the reference material agent's findings;
- tests, regenerate, commit.

## Task 3 checkpoint 3

- **Committed:** `8b1a197` (scope, polygons, confidence) and `371dca7` (0.7.0 interface and standard alignment). 92 tests pass (non-slow).
- **Design-standard study:** complete. Rules confirmed: SFP per column, splitters by remainder, pooled trays, OLM in Grant, MDU 1 per building, bulkhead rows 0. New rules adopted: boundary peds count as Grant, and the cable span goes to the ped it feeds.
- **Running:** the deliverable regeneration (`bash $S/regen9.sh`, writing to `$S/out9` with NMK_ref, NMK_new, DMI with reference, and DMF). After that:
  1. update PROGRESS_AND_ISSUES with the numbers;
  2. take browser screenshots with a tall window;
  3. run the slow test;
  4. commit, push, and send the files.

## Task 3 checkpoint 4 (0.7.1)

- **Confidence tuning:** done in `excel/confidence.py`.
  - Cable findings now go to their own fiber-count row and network.
  - A cable without a traced route is flagged only when its label and two ends are not all in one area (`CableSegment.split_uncertain`).
  - An address-layer conflict flags the residential count, and splitters or SFP only when the count would change.
  - The 0-written ped rows are flagged only for unmapped symbols on RTE_UGPOLES.
  - Reasons are aggregated.
  - The route and tray rules are VERIFIED (design standard); route_footage is removed from the unsettled list.
- **Tests:** 8 confidence tests.
- **Docs:** README, BOM_RULES, DESIGN_STANDARDS, CHANGELOG 0.7.1, PROGRESS_AND_ISSUES (0.7.0 numbers and DMF section).
- **Next:**
  1. integration tests (FTTX_TEST_DATA=$S/inputs);
  2. regenerate into `$S/out10`;
  3. compare the flag counts with out9;
  4. commit, push and send.

## Task 3 checkpoint 5

- **Committed:** `e31d491` (targeted confidence) and `40ce4b1` (preview table fix, closure-capacity targeting, pole-mount rating). 98 non-slow tests pass with the project data.
- **out10 vs out9 (before `40ce4b1`):** 0 quantity differences in all 7 BOMs.

  | BOM | Review cells, out9 → out10 |
  |---|---|
  | DMI | 48 → 20 |
  | NMK combined | 244 → 92 |
  | NMK-R02 | 64 → 26 |
  | NMK-R03 | 68 → 34 |
  | NMK-R04 | 56 → 16 |
  | NMK-R05 | 56 → 16 |
  | DMF | 12 → 10 |

  The low-confidence counts are unchanged.
- **Running:**
  - `regen11.sh` → `$S/out11` (final code);
  - app screenshots → `$S/shots5` (port 8602, HOME=`$S/apphome4`).
- **Next:**
  1. compare out11 with out9 (values identical);
  2. run the slow e2e test;
  3. update the PROGRESS flag counts;
  4. commit, push, send the files.

## Task 3 checkpoint 6 (final for this request)

- **out11 (final code) vs out9:** 0 quantity differences in all 7 BOMs.

  | BOM | Review cells, out9 → out11 |
  |---|---|
  | DMI | 48 → 18 |
  | NMK combined | 244 → 64 |
  | NMK-R02 | 64 → 14 |
  | NMK-R03 | 68 → 22 |
  | NMK-R04 | 56 → 14 |
  | NMK-R05 | 56 → 14 |
  | DMF | 12 → 8 |

  The low-confidence counts are unchanged.
- **Tests:** 98 non-slow tests plus the slow end-to-end test pass.
- **App screenshots:** `$S/shots5`, with no page errors. The preview table is fixed.
- **Delivered:** `$S/deliver` (outputs zip and screenshots zip).
- **Open decisions** (in PROGRESS_AND_ISSUES):
  - drop-footage columns;
  - MAX10 +4 policy;
  - D trays at DMI;
  - UG footage at DMI;
  - the template's bonding formulas.

# Progress

A workout tracker that tells you when you have stopped progressing.

Logging alone does not tell you anything. You can grind 30 kg × 10 for five
weeks straight, feel busy, and be going nowhere. This app's job is to notice
that and say so.

---

## What counts as progress

This is the rule the whole analytics layer is built on:

> **Progress is more reps at the same weight, or more weight. Nothing else.**

Three consequences, all deliberate:

- **An extra set is not progress.** Going from two sets of 30 × 10 to three sets
  of 30 × 10 is more total work, and the app will show you that volume went up —
  but it will still call the lift stalled. Total volume is reported as
  information and is never an input to the verdict.
- **Matching your best is not beating it.** Dipping to 30 × 9 one week and
  recovering to 30 × 10 the next is not a comeback; your best set never moved.
- **Warm-ups do not count.** They are excluded from every calculation — personal
  records, estimated 1RM, volume, and the stall verdict. That is the entire
  point of marking them.

A worked example. Chest press, one session per week:

| Week | Sets | Best set | Verdict |
|---|---|---|---|
| 1 | 30 × 10, 30 × 10 | 30 × 10 | building baseline |
| 2 | 30 × 10, 30 × 10 | 30 × 10 | building baseline |
| 3 | 30 × 9, 30 × 9 | 30 × 9 | no new best |
| 4 | 30 × 10, 30 × 10 | 30 × 10 | **stalled** |
| 5 | 30 × 10, 30 × 10 | 30 × 10 | **stalled** — beat it: 30 kg × 11 |

## How the verdict is computed

Each session, for each exercise, the app takes the **best qualifying set** and
scores it as an estimated 1RM using Epley, adjusted for reps in reserve:

```
e1RM = weight × (1 + (reps + RIR) / 30)          RIR = 10 − RPE
```

Estimated 1RM is the right metric here because it captures *both* halves of the
rule at once: adding a rep at the same weight raises it, and adding weight
raises it. A raw weight check would miss the first; a volume check would
wrongly reward the extra set.

The RPE adjustment matters too. 30 kg × 10 at RPE 10 and 30 kg × 10 at RPE 7 are
not the same performance, and scoring them identically is exactly how you
mistake real progress for a stall.

Above 15 reps the formula diverges badly, so those sets log normally but do not
score — a fake number is worse than no number.

From there:

| Verdict | Condition |
|---|---|
| **Building baseline** | fewer than 3 sessions logged |
| **Progressing** | a new best within the last 2 sessions |
| **Stalled** | no new best for 3 sessions (configurable, 2–5) |
| **Regressing** | best has fallen more than 5% and has not recovered |

Which set types feed which calculation:

| Set type | Sets records / drives progression | Counts toward volume |
|---|---|---|
| working, AMRAP, failure | yes | yes |
| drop, back-off | no | yes |
| warm-up | no | no |

Drop and back-off sets are performed pre-fatigued, so letting them set a record
would understate your real strength.

## Stack

| Concern | Choice |
|---|---|
| App | Vite + React 19 + TypeScript, static SPA |
| Styling | Tailwind v4 (CSS-first config, no JS config file) |
| Data | Supabase — Postgres, Auth, Row Level Security |
| Hosting | Cloudflare Pages, git-connected |
| Server state | TanStack Query |

No server runtime and no build adapter: the output is plain static files, which
is the least breakable thing to own long-term.

## Getting started

```bash
npm install
cp .env.example .env.local     # add your Supabase URL and anon key
npm run dev
```

Full setup — creating the database, running the migrations, deploying — is in
**[DEPLOY.md](./DEPLOY.md)**.

| Script | Does |
|---|---|
| `npm run dev` | Dev server at <http://localhost:5173> |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run typecheck` | TypeScript, no emit |
| `npm test` | Vitest |

## Layout

```
supabase/
  migrations/0001_schema.sql   tables, constraints, signup trigger
  migrations/0002_rls.sql      Row Level Security — the entire security boundary
  migrations/0003_views.sql    e1rm() and v_exercise_session_bests
  seed/exercises.sql           123 built-in exercises
src/
  lib/supabase.ts              client
  lib/types.ts                 database types, set-type rules
  lib/units.ts                 kg ↔ lb, formatting
  features/auth/               provider, login
  components/                  layout, bottom nav, UI kit
  routes/                      Today, Routines, History, Progress, Settings
```

### Two conventions worth knowing before you change anything

**All weight is stored in kilograms.** Unit preference is a display concern,
converted at the UI boundary in `src/lib/units.ts`. Mixing units in one column
silently corrupts every record, chart and verdict.

**RLS is the security boundary.** The anon key ships inside the JavaScript
bundle, where anyone can read it — that is by design and is safe *only* because
every table has Row Level Security enabled with explicit policies. Never add a
table without one.

## Roadmap

Built in slices, each one reviewable on its own.

- [x] **1 — Foundations.** Schema, RLS, auth, deployed shell, settings.
- [ ] **2 — Library and routines.** Browse and search exercises, add your own,
      build Leg Day and Chest Day.
- [ ] **3 — The logger.** Log sets against last session's numbers shown inline,
      warm-up and set-type chips, RPE, per-set notes, auto rest timer.
- [ ] **4 — Progression engine.** The verdict above, plus the Progress tab and
      the concrete next target for every stalled lift.
- [ ] **5 — Detail and records.** e1RM chart, full set history, rep-max table.

Later, roughly in order of value: plate calculator; weekly sets per muscle group
with MEV/MAV landmarks; warm-up ramp generator; deload prompts; per-side logging
and imbalance detection; substitution suggestions for stalled lifts; a proper
offline write queue.

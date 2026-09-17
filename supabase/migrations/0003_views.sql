-- ============================================================================
-- Progress - derived reads
--
-- SQL does the grouping (one row per workout+exercise instead of every set);
-- TypeScript decides the verdict. The verdict lives in src/lib/progression.ts
-- because it is the part we will iterate on and it needs to be unit-testable
-- against real training scenarios.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Estimated 1RM, Epley, adjusted for reps left in reserve.
--
--   e1RM = weight * (1 + (reps + RIR) / 30)      where RIR = 10 - RPE
--
-- The RPE adjustment matters: 30 kg x 10 @ RPE 10 and 30 kg x 10 @ RPE 7 are
-- not the same performance, and scoring them equally is exactly how you
-- mistake real progress for a stall.
--
-- Returns NULL above 15 reps - Epley diverges badly into high-rep territory and
-- a fake number is worse than no number. Those sets still log fine, they just
-- do not score.
-- ---------------------------------------------------------------------------
create or replace function public.e1rm(weight_kg numeric, reps smallint, rpe numeric)
returns numeric
language sql
immutable
set search_path = ''
as $$
  select case
    when weight_kg is null or weight_kg <= 0 then null
    when reps is null or reps <= 0 or reps > 15 then null
    else round(weight_kg * (1 + (reps + coalesce(10 - rpe, 0)) / 30.0), 2)
  end;
$$;

-- ---------------------------------------------------------------------------
-- One row per (workout, exercise): how that exercise went that session.
--
-- security_invoker = on is load-bearing. Postgres views run as their OWNER by
-- default, which would read straight through RLS and expose every user's sets.
-- With it on, the view is evaluated as the caller and the sets/workouts
-- policies apply normally.
-- ---------------------------------------------------------------------------
create or replace view public.v_exercise_session_bests
with (security_invoker = on) as
with scored as (
  select
    s.user_id,
    s.workout_id,
    s.exercise_id,
    w.started_at,
    s.set_type,
    s.weight_kg,
    s.reps,
    s.rpe,
    public.e1rm(s.weight_kg, s.reps, s.rpe)         as e1rm,
    s.set_type in ('working', 'amrap', 'failure')   as counts_for_progression,
    s.set_type <> 'warmup'                          as counts_for_volume
  from public.sets s
  join public.workouts w on w.id = s.workout_id
)
select
  user_id,
  workout_id,
  exercise_id,
  started_at,

  -- The progression signal. Warm-ups, drop sets and back-off sets are excluded.
  max(e1rm) filter (where counts_for_progression) as best_e1rm,

  -- The same set in human terms, for phrasing ("your best is still 30 kg x 10").
  (array_agg(weight_kg order by e1rm desc nulls last)
     filter (where counts_for_progression))[1]     as top_weight_kg,
  (array_agg(reps order by e1rm desc nulls last)
     filter (where counts_for_progression))[1]     as top_reps,
  (array_agg(rpe order by e1rm desc nulls last)
     filter (where counts_for_progression))[1]     as top_rpe,

  -- Volume is reported for information only and is deliberately NOT an input to
  -- the stall verdict: adding a fourth set is more work, but it is not progress.
  sum(coalesce(weight_kg, 0) * coalesce(reps, 0))
    filter (where counts_for_volume)               as volume_kg,
  count(*) filter (where counts_for_volume)        as working_set_count,
  count(*) filter (where set_type = 'warmup')      as warmup_set_count
from scored
group by user_id, workout_id, exercise_id, started_at;

grant select on public.v_exercise_session_bests to authenticated;

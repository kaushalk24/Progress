-- ============================================================================
-- Progress - core schema
--
-- Two conventions that hold everywhere and should not be broken later:
--
--  1. ALL WEIGHT IS STORED IN KILOGRAMS (weight_kg). Unit preference is a
--     display concern, converted at the UI boundary. Mixing units in one
--     column silently corrupts every PR, chart and progression verdict.
--
--  2. Every user-owned table carries user_id with `default auth.uid()`, so RLS
--     policies stay single-column comparisons instead of joins. Child tables
--     additionally use a COMPOSITE foreign key on (parent_id, user_id) so a
--     row can never be attached to someone else's parent - foreign keys
--     bypass RLS, so this is what actually enforces it.
-- ============================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- profiles : 1:1 with auth.users, holds per-user settings
-- ---------------------------------------------------------------------------
create table public.profiles (
  id                       uuid primary key references auth.users on delete cascade,
  display_name             text,
  unit                     text        not null default 'kg'
                             check (unit in ('kg', 'lb')),
  -- Same number, two presentations: RPE 8 == 2 reps in reserve.
  effort_display           text        not null default 'rir'
                             check (effort_display in ('rpe', 'rir')),
  default_rest_seconds     integer     not null default 120
                             check (default_rest_seconds between 0 and 1800),
  -- How many sessions without a new best before an exercise is called STALLED.
  -- 3 => flagged on the 4th flat session.
  stall_threshold_sessions smallint    not null default 3
                             check (stall_threshold_sessions between 2 and 10),
  bodyweight_kg            numeric(5,2) check (bodyweight_kg > 0),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

-- Create the profile row automatically on signup so the app never has to
-- handle a logged-in user with no settings.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)))
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- exercises : one table serves both the built-in library and custom lifts.
--   owner_id IS NULL  -> built-in, readable by everyone, editable by no one
--   owner_id = a user -> that user's own exercise
-- ---------------------------------------------------------------------------
create table public.exercises (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid references auth.users on delete cascade,
  name                text not null check (length(btrim(name)) between 1 and 80),
  primary_muscle      text not null check (primary_muscle in (
                        'chest','back','lats','traps','shoulders','biceps','triceps',
                        'forearms','quads','hamstrings','glutes','calves','abs',
                        'adductors','abductors','neck','full_body')),
  equipment           text not null check (equipment in (
                        'barbell','dumbbell','machine','cable','bodyweight','smith',
                        'kettlebell','band','plate','other')),
  is_unilateral       boolean not null default false,
  -- Drives the "what do I do next" target: fill the rep range, then add load.
  rep_min             smallint     not null default 8  check (rep_min  between 1 and 100),
  rep_max             smallint     not null default 12 check (rep_max  between 1 and 100),
  weight_increment_kg numeric(5,2) not null default 2.5 check (weight_increment_kg > 0),
  notes               text,
  created_at          timestamptz not null default now(),
  constraint exercises_rep_range_valid check (rep_max >= rep_min)
);

-- Case-insensitive uniqueness per owner. COALESCE gives built-ins a stable
-- sentinel owner so a NULL owner_id still participates in the unique index
-- (NULLs are otherwise all distinct from each other).
create unique index exercises_owner_name_key
  on public.exercises (coalesce(owner_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(btrim(name)));

create index exercises_owner_idx  on public.exercises (owner_id);
create index exercises_muscle_idx on public.exercises (primary_muscle);

-- ---------------------------------------------------------------------------
-- routines : "Leg day", "Chest day"
-- ---------------------------------------------------------------------------
create table public.routines (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  name        text not null check (length(btrim(name)) between 1 and 80),
  notes       text,
  position    integer not null default 0,
  archived_at timestamptz,
  created_at  timestamptz not null default now(),
  -- Target for the composite FK from routine_exercises.
  unique (id, user_id)
);

create index routines_user_idx on public.routines (user_id, position);

-- ---------------------------------------------------------------------------
-- routine_exercises : the template - which exercises, in what order
-- ---------------------------------------------------------------------------
create table public.routine_exercises (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users on delete cascade,
  routine_id     uuid not null,
  exercise_id    uuid not null references public.exercises on delete restrict,
  position       integer not null default 0,
  target_sets    smallint check (target_sets between 1 and 20),
  target_rep_min smallint check (target_rep_min between 1 and 100),
  target_rep_max smallint check (target_rep_max between 1 and 100),
  rest_seconds   integer  check (rest_seconds between 0 and 1800),
  notes          text,
  created_at     timestamptz not null default now(),
  -- Cannot attach to another user's routine, even though FKs ignore RLS.
  constraint routine_exercises_routine_fkey
    foreign key (routine_id, user_id) references public.routines (id, user_id) on delete cascade
);

create index routine_exercises_routine_idx on public.routine_exercises (routine_id, position);

-- ---------------------------------------------------------------------------
-- workouts : one logged session
-- ---------------------------------------------------------------------------
create table public.workouts (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users on delete cascade,
  routine_id    uuid references public.routines on delete set null,
  name          text not null default 'Workout',
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  notes         text,
  bodyweight_kg numeric(5,2) check (bodyweight_kg > 0),
  created_at    timestamptz not null default now(),
  unique (id, user_id)
);

create index workouts_user_started_idx on public.workouts (user_id, started_at desc);

-- ---------------------------------------------------------------------------
-- sets : the atom. Every set ever performed.
--
-- set_type drives two rules used by every analytic in the app:
--   counts for progression : working | amrap | failure
--   counts for volume      : anything except warmup
-- Drop and back-off sets are performed pre-fatigued, so letting them set a PR
-- would understate real strength. Warm-ups are excluded from everything.
-- ---------------------------------------------------------------------------
create table public.sets (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references auth.users on delete cascade,
  workout_id       uuid not null,
  exercise_id      uuid not null references public.exercises on delete restrict,
  position         integer not null default 0,
  set_type         text not null default 'working'
                     check (set_type in ('working','warmup','drop','failure','amrap','backoff')),
  -- NULL for unloaded bodyweight work; for weighted pull-ups this is the ADDED load.
  weight_kg        numeric(6,2) check (weight_kg >= 0),
  reps             smallint     check (reps between 0 and 1000),
  rpe              numeric(3,1) check (rpe between 5 and 10),
  rest_seconds     integer      check (rest_seconds between 0 and 7200),
  -- Reserved for time/distance work (planks, carries, cardio). No UI yet; these
  -- exist so adding it later is not a migration on a live table.
  duration_seconds integer      check (duration_seconds >= 0),
  distance_m       numeric(8,2) check (distance_m >= 0),
  notes            text,
  completed_at     timestamptz not null default now(),
  created_at       timestamptz not null default now(),
  constraint sets_workout_fkey
    foreign key (workout_id, user_id) references public.workouts (id, user_id) on delete cascade
);

create index sets_workout_idx  on public.sets (workout_id, position);
-- The index the progression engine leans on: "every set of exercise X, newest first".
create index sets_user_exercise_idx on public.sets (user_id, exercise_id, completed_at desc);

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();

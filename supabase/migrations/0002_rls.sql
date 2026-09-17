-- ============================================================================
-- Progress - Row Level Security
--
-- The anon key is PUBLIC: it ships inside the JavaScript bundle that anyone can
-- download. RLS is therefore the entire security boundary of this application.
-- Every table below is force-enabled and has explicit policies. There are no
-- exceptions and no table should ever be added without one.
--
-- Note the `(select auth.uid())` wrapping. Postgres evaluates the subquery once
-- per statement instead of once per row, which turns a sequential re-evaluation
-- into a single initplan - a large difference on set history queries.
-- ============================================================================

alter table public.profiles          enable row level security;
alter table public.exercises         enable row level security;
alter table public.routines          enable row level security;
alter table public.routine_exercises enable row level security;
alter table public.workouts          enable row level security;
alter table public.sets              enable row level security;

-- ---------------------------------------------------------------------------
-- profiles : yours and only yours. No delete policy - profiles die with the
-- auth.users row via ON DELETE CASCADE.
-- ---------------------------------------------------------------------------
create policy "profiles: read own" on public.profiles
  for select to authenticated using (id = (select auth.uid()));

create policy "profiles: insert own" on public.profiles
  for insert to authenticated with check (id = (select auth.uid()));

create policy "profiles: update own" on public.profiles
  for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- exercises : everyone reads the built-in library (owner_id IS NULL) plus their
-- own custom lifts. Writes are restricted to rows you own, which makes the
-- built-in library readable-but-immutable to every user - there is deliberately
-- no policy under which owner_id IS NULL rows can be updated or deleted.
-- ---------------------------------------------------------------------------
create policy "exercises: read built-in and own" on public.exercises
  for select to authenticated
  using (owner_id is null or owner_id = (select auth.uid()));

create policy "exercises: insert own" on public.exercises
  for insert to authenticated with check (owner_id = (select auth.uid()));

create policy "exercises: update own" on public.exercises
  for update to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create policy "exercises: delete own" on public.exercises
  for delete to authenticated using (owner_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- routines / routine_exercises / workouts / sets : straightforward ownership.
-- ---------------------------------------------------------------------------
create policy "routines: all own" on public.routines
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "routine_exercises: all own" on public.routine_exercises
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "workouts: all own" on public.workouts
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "sets: all own" on public.sets
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

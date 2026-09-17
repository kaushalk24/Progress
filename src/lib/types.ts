/**
 * Database types, hand-maintained to match supabase/migrations/.
 *
 * Once the project is live these can be regenerated instead:
 *   npx supabase gen types typescript --project-id <ref> > src/lib/types.ts
 *
 * Reminder: every weight column is KILOGRAMS. Convert at the UI boundary only
 * (see units.ts) - never store a pound value in a *_kg column.
 */

export const MUSCLE_GROUPS = [
  'chest', 'back', 'lats', 'traps', 'shoulders', 'biceps', 'triceps',
  'forearms', 'quads', 'hamstrings', 'glutes', 'calves', 'abs',
  'adductors', 'abductors', 'neck', 'full_body',
] as const
export type MuscleGroup = (typeof MUSCLE_GROUPS)[number]

export const EQUIPMENT = [
  'barbell', 'dumbbell', 'machine', 'cable', 'bodyweight', 'smith',
  'kettlebell', 'band', 'plate', 'other',
] as const
export type Equipment = (typeof EQUIPMENT)[number]

export const SET_TYPES = ['working', 'warmup', 'drop', 'failure', 'amrap', 'backoff'] as const
export type SetType = (typeof SET_TYPES)[number]

/**
 * The two rules every analytic in the app obeys.
 *
 * Drop and back-off sets are performed pre-fatigued, so counting them toward a
 * personal record would understate real strength. Warm-ups are excluded from
 * everything - that is the entire point of marking them.
 *
 * These MUST stay in step with the same expressions in 0003_views.sql.
 */
export const countsForProgression = (t: SetType): boolean =>
  t === 'working' || t === 'amrap' || t === 'failure'

export const countsForVolume = (t: SetType): boolean => t !== 'warmup'

/**
 * These are type aliases, not interfaces, on purpose: supabase-js constrains
 * table rows to Record<string, unknown>, and a TypeScript interface has no
 * implicit index signature to satisfy that. Converting them to interfaces
 * makes every query argument resolve to `never`.
 */
export type Unit = 'kg' | 'lb'
export type EffortDisplay = 'rpe' | 'rir'

export type Profile = {
  id: string
  display_name: string | null
  unit: Unit
  effort_display: EffortDisplay
  default_rest_seconds: number
  stall_threshold_sessions: number
  bodyweight_kg: number | null
  created_at: string
  updated_at: string
}

export type Exercise = {
  id: string
  /** null = built-in library entry: readable by all, editable by none. */
  owner_id: string | null
  name: string
  primary_muscle: MuscleGroup
  equipment: Equipment
  is_unilateral: boolean
  rep_min: number
  rep_max: number
  weight_increment_kg: number
  notes: string | null
  created_at: string
}

export type Routine = {
  id: string
  user_id: string
  name: string
  notes: string | null
  position: number
  archived_at: string | null
  created_at: string
}

export type RoutineExercise = {
  id: string
  user_id: string
  routine_id: string
  exercise_id: string
  position: number
  target_sets: number | null
  target_rep_min: number | null
  target_rep_max: number | null
  rest_seconds: number | null
  notes: string | null
  created_at: string
}

export type Workout = {
  id: string
  user_id: string
  routine_id: string | null
  name: string
  started_at: string
  finished_at: string | null
  notes: string | null
  bodyweight_kg: number | null
  created_at: string
}

export type WorkoutSet = {
  id: string
  user_id: string
  workout_id: string
  exercise_id: string
  position: number
  set_type: SetType
  /** NULL for unloaded bodyweight work; ADDED load for weighted bodyweight work. */
  weight_kg: number | null
  reps: number | null
  rpe: number | null
  rest_seconds: number | null
  duration_seconds: number | null
  distance_m: number | null
  notes: string | null
  completed_at: string
  created_at: string
}

/** One row per (workout, exercise) from v_exercise_session_bests. */
export type ExerciseSessionBest = {
  user_id: string
  workout_id: string
  exercise_id: string
  started_at: string
  best_e1rm: number | null
  top_weight_kg: number | null
  top_reps: number | null
  top_rpe: number | null
  /** Information only. Deliberately not an input to the stall verdict. */
  volume_kg: number | null
  working_set_count: number
  warmup_set_count: number
}

/** Columns the database fills in for us on insert. */
type Generated = 'id' | 'user_id' | 'created_at'

type TableDef<Row, Optional extends keyof Row = never> = {
  Row: Row
  Insert: Omit<Row, Generated | Optional> & Partial<Pick<Row, Extract<Generated | Optional, keyof Row>>>
  Update: Partial<Row>
  Relationships: []
}

export type Database = {
  public: {
    Tables: {
      profiles: {
        Row: Profile
        Insert: Pick<Profile, 'id'> & Partial<Profile>
        Update: Partial<Profile>
        Relationships: []
      }
      exercises: TableDef<Exercise, 'owner_id' | 'is_unilateral' | 'rep_min' | 'rep_max' | 'weight_increment_kg' | 'notes'>
      routines: TableDef<Routine, 'notes' | 'position' | 'archived_at'>
      routine_exercises: TableDef<RoutineExercise, 'position' | 'target_sets' | 'target_rep_min' | 'target_rep_max' | 'rest_seconds' | 'notes'>
      workouts: TableDef<Workout, 'routine_id' | 'name' | 'started_at' | 'finished_at' | 'notes' | 'bodyweight_kg'>
      sets: TableDef<WorkoutSet, 'position' | 'set_type' | 'weight_kg' | 'reps' | 'rpe' | 'rest_seconds' | 'duration_seconds' | 'distance_m' | 'notes' | 'completed_at'>
    }
    Views: {
      v_exercise_session_bests: {
        Row: ExerciseSessionBest
        Relationships: []
      }
    }
    Functions: {
      e1rm: {
        Args: { weight_kg: number | null; reps: number | null; rpe: number | null }
        Returns: number | null
      }
    }
    Enums: Record<never, never>
    CompositeTypes: Record<never, never>
  }
}

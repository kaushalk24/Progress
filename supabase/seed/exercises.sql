-- ============================================================================
-- Progress - built-in exercise library
--
-- owner_id IS NULL marks these as built-in: every user can read and use them,
-- nobody can edit or delete them (see 0002_rls.sql). Custom lifts a user adds
-- carry their own owner_id and live alongside these in the same table.
--
-- Safe to re-run: ON CONFLICT DO NOTHING against the case-insensitive unique
-- index, so re-running after adding rows below only inserts the new ones.
--
-- Defaults are training-sensible rather than uniform:
--   rep_min/rep_max      heavy compounds 5-8, accessories 8-12, isolation 10-15,
--                        calves and abs 12-20
--   weight_increment_kg  barbell 2.5, dumbbell 2 (pairs go up in 2s), machines
--                        and cables 5 (most stacks), bodyweight 2.5 (added load)
-- ============================================================================

insert into public.exercises
  (owner_id, name, primary_muscle, equipment, is_unilateral, rep_min, rep_max, weight_increment_kg)
values
-- ---- Chest ----------------------------------------------------------------
(null, 'Barbell Bench Press',          'chest', 'barbell',    false,  5, 8, 2.5),
(null, 'Incline Barbell Bench Press',  'chest', 'barbell',    false,  6, 10, 2.5),
(null, 'Decline Barbell Bench Press',  'chest', 'barbell',    false,  6, 10, 2.5),
(null, 'Smith Machine Bench Press',    'chest', 'smith',      false,  6, 10, 2.5),
(null, 'Dumbbell Bench Press',         'chest', 'dumbbell',   false,  6, 12, 2),
(null, 'Incline Dumbbell Bench Press', 'chest', 'dumbbell',   false,  8, 12, 2),
(null, 'Decline Dumbbell Bench Press', 'chest', 'dumbbell',   false,  8, 12, 2),
(null, 'Dumbbell Fly',                 'chest', 'dumbbell',   false, 10, 15, 2),
(null, 'Incline Dumbbell Fly',         'chest', 'dumbbell',   false, 10, 15, 2),
(null, 'Cable Fly',                    'chest', 'cable',      false, 10, 15, 5),
(null, 'Low-to-High Cable Fly',        'chest', 'cable',      false, 10, 15, 5),
(null, 'High-to-Low Cable Fly',        'chest', 'cable',      false, 10, 15, 5),
(null, 'Machine Chest Press',          'chest', 'machine',    false,  8, 12, 5),
(null, 'Incline Machine Press',        'chest', 'machine',    false,  8, 12, 5),
(null, 'Pec Deck',                     'chest', 'machine',    false, 10, 15, 5),
(null, 'Push-Up',                      'chest', 'bodyweight', false, 10, 20, 2.5),
(null, 'Chest Dip',                    'chest', 'bodyweight', false,  6, 12, 2.5),

-- ---- Back and lats --------------------------------------------------------
(null, 'Deadlift',                     'back',  'barbell',    false,  3, 6, 5),
(null, 'Trap Bar Deadlift',            'back',  'barbell',    false,  5, 8, 5),
(null, 'Rack Pull',                    'back',  'barbell',    false,  5, 8, 5),
(null, 'Barbell Row',                  'back',  'barbell',    false,  6, 10, 2.5),
(null, 'Pendlay Row',                  'back',  'barbell',    false,  5, 8, 2.5),
(null, 'T-Bar Row',                    'back',  'barbell',    false,  8, 12, 2.5),
(null, 'Dumbbell Row',                 'back',  'dumbbell',   true,   8, 12, 2),
(null, 'Chest-Supported Row',          'back',  'dumbbell',   false,  8, 12, 2),
(null, 'Meadows Row',                  'back',  'barbell',    true,   8, 12, 2.5),
(null, 'Seated Cable Row',             'back',  'cable',      false,  8, 12, 5),
(null, 'Machine Row',                  'back',  'machine',    false,  8, 12, 5),
(null, 'Inverted Row',                 'back',  'bodyweight', false,  8, 15, 2.5),
(null, 'Pull-Up',                      'lats',  'bodyweight', false,  5, 10, 2.5),
(null, 'Chin-Up',                      'lats',  'bodyweight', false,  5, 10, 2.5),
(null, 'Lat Pulldown',                 'lats',  'cable',      false,  8, 12, 5),
(null, 'Wide-Grip Lat Pulldown',       'lats',  'cable',      false,  8, 12, 5),
(null, 'Close-Grip Lat Pulldown',      'lats',  'cable',      false,  8, 12, 5),
(null, 'Straight-Arm Pulldown',        'lats',  'cable',      false, 10, 15, 5),
(null, 'Barbell Shrug',                'traps', 'barbell',    false,  8, 12, 2.5),
(null, 'Dumbbell Shrug',               'traps', 'dumbbell',   false, 10, 15, 2),
(null, 'Face Pull',                    'traps', 'cable',      false, 12, 20, 5),

-- ---- Shoulders ------------------------------------------------------------
(null, 'Overhead Press',               'shoulders', 'barbell',    false,  5, 8, 2.5),
(null, 'Push Press',                   'shoulders', 'barbell',    false,  3, 6, 2.5),
(null, 'Seated Barbell Press',         'shoulders', 'barbell',    false,  6, 10, 2.5),
(null, 'Seated Dumbbell Press',        'shoulders', 'dumbbell',   false,  8, 12, 2),
(null, 'Arnold Press',                 'shoulders', 'dumbbell',   false,  8, 12, 2),
(null, 'Machine Shoulder Press',       'shoulders', 'machine',    false,  8, 12, 5),
(null, 'Landmine Press',               'shoulders', 'barbell',    true,   8, 12, 2.5),
(null, 'Dumbbell Lateral Raise',       'shoulders', 'dumbbell',   false, 12, 20, 2),
(null, 'Cable Lateral Raise',          'shoulders', 'cable',      true,  12, 20, 5),
(null, 'Machine Lateral Raise',        'shoulders', 'machine',    false, 12, 20, 5),
(null, 'Dumbbell Front Raise',         'shoulders', 'dumbbell',   false, 10, 15, 2),
(null, 'Rear Delt Fly',                'shoulders', 'dumbbell',   false, 12, 20, 2),
(null, 'Reverse Pec Deck',             'shoulders', 'machine',    false, 12, 20, 5),
(null, 'Upright Row',                  'shoulders', 'barbell',    false, 10, 15, 2.5),

-- ---- Biceps ---------------------------------------------------------------
(null, 'Barbell Curl',                 'biceps', 'barbell',  false,  8, 12, 2.5),
(null, 'EZ-Bar Curl',                  'biceps', 'barbell',  false,  8, 12, 2.5),
(null, 'Dumbbell Curl',                'biceps', 'dumbbell', false, 10, 15, 2),
(null, 'Incline Dumbbell Curl',        'biceps', 'dumbbell', false, 10, 15, 2),
(null, 'Hammer Curl',                  'biceps', 'dumbbell', false, 10, 15, 2),
(null, 'Preacher Curl',                'biceps', 'barbell',  false, 10, 15, 2.5),
(null, 'Cable Curl',                   'biceps', 'cable',    false, 10, 15, 5),
(null, 'Concentration Curl',           'biceps', 'dumbbell', true,  10, 15, 2),
(null, 'Spider Curl',                  'biceps', 'dumbbell', false, 10, 15, 2),
(null, 'Machine Curl',                 'biceps', 'machine',  false, 10, 15, 5),

-- ---- Triceps --------------------------------------------------------------
(null, 'Close-Grip Bench Press',       'triceps', 'barbell',    false,  6, 10, 2.5),
(null, 'JM Press',                     'triceps', 'barbell',    false,  8, 12, 2.5),
(null, 'Skullcrusher',                 'triceps', 'barbell',    false,  8, 12, 2.5),
(null, 'Tricep Pushdown',              'triceps', 'cable',      false, 10, 15, 5),
(null, 'Rope Pushdown',                'triceps', 'cable',      false, 10, 15, 5),
(null, 'Overhead Tricep Extension',    'triceps', 'cable',      false, 10, 15, 5),
(null, 'Dumbbell Overhead Extension',  'triceps', 'dumbbell',   false, 10, 15, 2),
(null, 'Tricep Kickback',              'triceps', 'dumbbell',   true,  12, 20, 2),
(null, 'Triceps Dip',                  'triceps', 'bodyweight', false,  6, 12, 2.5),
(null, 'Bench Dip',                    'triceps', 'bodyweight', false, 10, 20, 2.5),

-- ---- Forearms -------------------------------------------------------------
(null, 'Wrist Curl',                   'forearms', 'barbell',    false, 12, 20, 2.5),
(null, 'Reverse Wrist Curl',           'forearms', 'barbell',    false, 12, 20, 2.5),
(null, 'Reverse Curl',                 'forearms', 'barbell',    false, 10, 15, 2.5),
(null, 'Farmer''s Carry',              'forearms', 'dumbbell',   false,  1, 3, 2),

-- ---- Quads ----------------------------------------------------------------
(null, 'Back Squat',                   'quads', 'barbell',    false,  5, 8, 2.5),
(null, 'Front Squat',                  'quads', 'barbell',    false,  5, 8, 2.5),
(null, 'Smith Machine Squat',          'quads', 'smith',      false,  8, 12, 2.5),
(null, 'Hack Squat',                   'quads', 'machine',    false,  8, 12, 5),
(null, 'Leg Press',                    'quads', 'machine',    false,  8, 15, 5),
(null, 'Goblet Squat',                 'quads', 'dumbbell',   false, 10, 15, 2),
(null, 'Bulgarian Split Squat',        'quads', 'dumbbell',   true,   8, 12, 2),
(null, 'Walking Lunge',                'quads', 'dumbbell',   true,  10, 15, 2),
(null, 'Reverse Lunge',                'quads', 'dumbbell',   true,  10, 15, 2),
(null, 'Step-Up',                      'quads', 'dumbbell',   true,  10, 15, 2),
(null, 'Leg Extension',                'quads', 'machine',    false, 12, 15, 5),
(null, 'Sissy Squat',                  'quads', 'bodyweight', false, 10, 15, 2.5),

-- ---- Hamstrings -----------------------------------------------------------
(null, 'Romanian Deadlift',            'hamstrings', 'barbell',    false,  6, 10, 2.5),
(null, 'Stiff-Leg Deadlift',           'hamstrings', 'barbell',    false,  8, 12, 2.5),
(null, 'Single-Leg Romanian Deadlift', 'hamstrings', 'dumbbell',   true,  10, 15, 2),
(null, 'Lying Leg Curl',               'hamstrings', 'machine',    false, 10, 15, 5),
(null, 'Seated Leg Curl',              'hamstrings', 'machine',    false, 10, 15, 5),
(null, 'Nordic Hamstring Curl',        'hamstrings', 'bodyweight', false,  5, 10, 2.5),
(null, 'Good Morning',                 'hamstrings', 'barbell',    false,  8, 12, 2.5),
(null, 'Glute-Ham Raise',              'hamstrings', 'bodyweight', false,  8, 12, 2.5),

-- ---- Glutes ---------------------------------------------------------------
(null, 'Hip Thrust',                   'glutes', 'barbell',    false,  8, 12, 2.5),
(null, 'Barbell Glute Bridge',         'glutes', 'barbell',    false,  8, 12, 2.5),
(null, 'Machine Hip Thrust',           'glutes', 'machine',    false, 10, 15, 5),
(null, 'Cable Glute Kickback',         'glutes', 'cable',      true,  12, 20, 5),
(null, 'Back Extension',               'glutes', 'bodyweight', false, 10, 15, 2.5),
(null, 'Reverse Hyperextension',       'glutes', 'machine',    false, 10, 15, 5),

-- ---- Calves ---------------------------------------------------------------
(null, 'Standing Calf Raise',          'calves', 'machine', false, 12, 20, 5),
(null, 'Seated Calf Raise',            'calves', 'machine', false, 12, 20, 5),
(null, 'Leg Press Calf Raise',         'calves', 'machine', false, 12, 20, 5),
(null, 'Smith Machine Calf Raise',     'calves', 'smith',   false, 12, 20, 2.5),

-- ---- Abs ------------------------------------------------------------------
(null, 'Cable Crunch',                 'abs', 'cable',      false, 12, 20, 5),
(null, 'Hanging Leg Raise',            'abs', 'bodyweight', false, 10, 15, 2.5),
(null, 'Hanging Knee Raise',           'abs', 'bodyweight', false, 12, 20, 2.5),
(null, 'Ab Wheel Rollout',             'abs', 'bodyweight', false, 10, 15, 2.5),
(null, 'Decline Sit-Up',               'abs', 'bodyweight', false, 12, 20, 2.5),
(null, 'Machine Crunch',               'abs', 'machine',    false, 12, 20, 5),
(null, 'Russian Twist',                'abs', 'plate',      false, 15, 25, 2.5),
(null, 'Plank',                        'abs', 'bodyweight', false,  1, 3, 2.5),

-- ---- Hips and neck --------------------------------------------------------
(null, 'Hip Adduction Machine',        'adductors', 'machine', false, 12, 20, 5),
(null, 'Hip Abduction Machine',        'abductors', 'machine', false, 12, 20, 5),
(null, 'Cable Hip Abduction',          'abductors', 'cable',   true,  12, 20, 5),
(null, 'Neck Curl',                    'neck',      'plate',   false, 12, 20, 1.25),
(null, 'Neck Extension',               'neck',      'plate',   false, 12, 20, 1.25),

-- ---- Full body ------------------------------------------------------------
(null, 'Power Clean',                  'full_body', 'barbell',   false, 2, 5, 2.5),
(null, 'Hang Clean',                   'full_body', 'barbell',   false, 3, 5, 2.5),
(null, 'Thruster',                     'full_body', 'barbell',   false, 6, 10, 2.5),
(null, 'Kettlebell Swing',             'full_body', 'kettlebell', false, 12, 20, 4)
on conflict do nothing;

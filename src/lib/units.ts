import type { Unit } from './types'

const LB_PER_KG = 2.20462262185

/** Storage (always kg) -> what the user sees. */
export function fromKg(kg: number, unit: Unit): number {
  return unit === 'lb' ? kg * LB_PER_KG : kg
}

/** What the user typed -> storage (always kg). */
export function toKg(value: number, unit: Unit): number {
  return unit === 'lb' ? value / LB_PER_KG : value
}

/**
 * Trim trailing zeros so 2.50 reads as "2.5" and 100.00 as "100". Weights on a
 * bar are read at a glance between sets; the noise is not free.
 */
export function formatNumber(n: number, maxDecimals = 2): string {
  return Number(n.toFixed(maxDecimals)).toString()
}

export function formatWeight(kg: number | null, unit: Unit): string {
  if (kg === null) return 'BW'
  return `${formatNumber(fromKg(kg, unit), 1)} ${unit}`
}

/** "30 kg x 10" - the canonical way a set is written throughout the app. */
export function formatSet(kg: number | null, reps: number | null, unit: Unit): string {
  const r = reps ?? 0
  return kg === null ? `BW x ${r}` : `${formatNumber(fromKg(kg, unit), 1)} ${unit} x ${r}`
}

/** RPE 8 and "2 in reserve" are the same number wearing different clothes. */
export function rpeToRir(rpe: number): number {
  return 10 - rpe
}

export function rirToRpe(rir: number): number {
  return 10 - rir
}

/** 185 -> "3:05". Used by the rest timer and session durations. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m)
  return h > 0
    ? `${h}:${mm}:${String(sec).padStart(2, '0')}`
    : `${mm}:${String(sec).padStart(2, '0')}`
}

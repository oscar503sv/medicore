import type { TimeRange } from '@/types'

// Monday-first, matching the backend's weekday index (0 = Monday).
export const DAY_KEYS = [
  'day.mon',
  'day.tue',
  'day.wed',
  'day.thu',
  'day.fri',
  'day.sat',
  'day.sun',
]
// Fixed grid of selectable times (07:00–22:00 every 15 min) — selects, not free text,
// so a block can never hold an invalid value (SPEC PARTE E.1).
export const TIME_OPTIONS: string[] = (() => {
  const out: string[] = []
  for (let m = 7 * 60; m <= 22 * 60; m += 15) {
    out.push(`${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`)
  }
  return out
})()

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export function blocksMinutes(blocks: TimeRange[]): number {
  return blocks.reduce((sum, b) => sum + Math.max(0, toMinutes(b.end) - toMinutes(b.start)), 0)
}

import type { DoseStatus, ScheduledDose } from '@/api/vaccinations'
import type { Tone } from '@/components/ui/badgeTone'

type T = (key: string) => string

const fill = (s: string, n: string | number) => s.replace('{n}', String(n))

export const vaccineName = (t: T, code: string) => {
  const key = `vax.name.${code}`
  const label = t(key)
  return label === key ? code : label
}

export const vaccineDiseases = (t: T, code: string) => {
  const key = `vax.diseases.${code}`
  const label = t(key)
  return label === key ? '' : label
}

/** "Dosis 2", "Refuerzo 1", "Dosis única", "Anual", "Cada 10 años". */
export function doseLabel(t: T, dose: ScheduledDose): string {
  if (dose.kind === 'periodic') return fill(t('vax.kind.periodic'), (dose.repeat_months ?? 0) / 12)
  return fill(t(`vax.kind.${dose.kind}`), dose.number)
}

/** Recommended age: "Al nacer", "4 meses", "18 meses", "10 años". */
export function ageLabel(t: T, months: number): string {
  if (months === 0) return t('vax.age.birth')
  if (months < 24) return fill(t('vax.age.months'), months)
  return fill(t('vax.age.years'), Math.floor(months / 12))
}

export const STATUS_TONE: Record<DoseStatus, Tone> = {
  administered: 'ok',
  refused: 'warn',
  contraindicated: 'warn',
  overdue: 'danger',
  due: 'warn',
  due_soon: 'info',
  upcoming: 'neutral',
  not_applicable: 'neutral',
  indicated: 'accent',
}

/** Doses still to be chased (drive the counters and the worklist). */
export const isPending = (s: DoseStatus) => s === 'due' || s === 'overdue'

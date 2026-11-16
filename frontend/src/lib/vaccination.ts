import type {
  DoseState,
  DoseStatus,
  ScheduledDose,
  VaccinationCatalog,
} from '@/api/vaccinations'
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

/** Doses of a vaccine that apply to this patient and can still be recorded (periodic doses
 * repeat, so they are always offered; a dose with no state belongs to the other sex). */
export function openDoses(
  catalog: VaccinationCatalog,
  states: DoseState[],
  vaccine: string,
): ScheduledDose[] {
  const stateByKey = new Map(states.map((s) => [s.key, s]))
  return catalog.doses.filter((d) => {
    if (d.vaccine !== vaccine) return false
    const st = stateByKey.get(d.key)
    return !!st && (d.repeat_months != null || st.status !== 'administered')
  })
}

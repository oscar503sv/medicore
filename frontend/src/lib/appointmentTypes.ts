import type { Tone } from '@/components/ui/badgeTone'
import type { AppointmentType } from '@/types'

// Single source of truth for appointment types. `priced` mirrors the backend fee schedule:
// procedures are charged from the procedure catalog, not from a per-doctor fee.
const META = {
  consult: { priced: true, tone: 'info' },
  follow_up: { priced: true, tone: 'accent' },
  check_up: { priced: true, tone: 'ok' },
  emergency: { priced: true, tone: 'danger' },
  procedure: { priced: false, tone: 'warn' },
} as const satisfies Record<AppointmentType, { priced: boolean; tone: Tone }>

export const APPOINTMENT_TYPES = Object.keys(META) as AppointmentType[]
export const PRICED_TYPES = APPOINTMENT_TYPES.filter((t) => META[t].priced)

export const typeLabelKey = (t: AppointmentType) => `apptype.${t}`
export const typeHintKey = (t: AppointmentType) => `apptype.${t}_hint`
export const typeTone = (t: string): Tone => META[t as AppointmentType]?.tone ?? 'neutral'
export const isAppointmentType = (v: string): v is AppointmentType => v in META

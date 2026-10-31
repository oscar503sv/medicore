import { Activity, Droplet, Gauge, HeartPulse, Thermometer, Weight, type LucideIcon } from 'lucide-react'
import type { Vitals } from '@/types'

export interface VitalCol {
  key: keyof Vitals
  labelKey: string
  unit: string // literal unit or a `vital.unit_*` i18n key — render with unitLabel()
  icon: LucideIcon
  fmt: (v: NonNullable<Vitals[keyof Vitals]>) => string
}

/** Columns shown for vitals — short labels mirror the consultation/record drawer. */
export const VITAL_COLS: VitalCol[] = [
  { key: 'blood_pressure', labelKey: 'vital.blood_pressure', unit: 'mmHg', icon: Gauge, fmt: (v) => String(v) },
  { key: 'heart_rate', labelKey: 'vital.heart_rate', unit: 'vital.unit_bpm', icon: HeartPulse, fmt: (v) => String(v) },
  { key: 'spo2', labelKey: 'vital.spo2', unit: '%', icon: Activity, fmt: (v) => String(v) },
  { key: 'temperature', labelKey: 'vital.temperature', unit: '°C', icon: Thermometer, fmt: (v) => String(v) },
  { key: 'weight', labelKey: 'vital.weight', unit: 'kg', icon: Weight, fmt: (v) => String(v) },
  { key: 'glucose', labelKey: 'vital.glucose', unit: 'mg/dL', icon: Droplet, fmt: (v) => String(v) },
]

/** Units are literal ("mmHg") except language-dependent ones, stored as i18n keys. */
export const unitLabel = (t: (key: string) => string, unit: string) =>
  unit.startsWith('vital.') ? t(unit) : unit

export const hasAnyVital = (v: Vitals) => VITAL_COLS.some((c) => v[c.key] != null)

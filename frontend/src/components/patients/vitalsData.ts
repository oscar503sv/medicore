import { Activity, Droplet, Gauge, HeartPulse, Thermometer, Weight, type LucideIcon } from 'lucide-react'
import type { Vitals } from '@/types'

export interface VitalCol {
  key: keyof Vitals
  label: string
  unit: string
  icon: LucideIcon
  fmt: (v: NonNullable<Vitals[keyof Vitals]>) => string
}

/** Columns shown for vitals — short labels mirror the consultation/record drawer. */
export const VITAL_COLS: VitalCol[] = [
  { key: 'blood_pressure', label: 'TA', unit: 'mmHg', icon: Gauge, fmt: (v) => String(v) },
  { key: 'heart_rate', label: 'FC', unit: 'lpm', icon: HeartPulse, fmt: (v) => String(v) },
  { key: 'spo2', label: 'SpO₂', unit: '%', icon: Activity, fmt: (v) => String(v) },
  { key: 'temperature', label: 'Temp', unit: '°C', icon: Thermometer, fmt: (v) => String(v) },
  { key: 'weight', label: 'Peso', unit: 'kg', icon: Weight, fmt: (v) => String(v) },
  { key: 'glucose', label: 'Gluc', unit: 'mg/dL', icon: Droplet, fmt: (v) => String(v) },
]

export const hasAnyVital = (v: Vitals) => VITAL_COLS.some((c) => v[c.key] != null)

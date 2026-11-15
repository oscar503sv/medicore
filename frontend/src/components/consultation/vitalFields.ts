import type { Vitals } from '@/types'

export interface VitalField {
  key: keyof Vitals
  labelKey: string
  placeholder: string
  unit: string // literal unit or a `vital.unit_*` i18n key
}

export const VITAL_FIELDS: VitalField[] = [
  { key: 'blood_pressure', labelKey: 'vital.blood_pressure', placeholder: '120/80', unit: 'mmHg' },
  { key: 'heart_rate', labelKey: 'vital.heart_rate', placeholder: '72', unit: 'vital.unit_bpm' },
  { key: 'spo2', labelKey: 'vital.spo2', placeholder: '98', unit: '%' },
  { key: 'temperature', labelKey: 'vital.temperature', placeholder: '36.5', unit: '°C' },
  { key: 'weight', labelKey: 'vital.weight', placeholder: '70', unit: 'kg' },
  { key: 'glucose', labelKey: 'vital.glucose_full', placeholder: '90', unit: 'mg/dL' },
]

const INTEGER_FIELDS = new Set<keyof Vitals>(['heart_rate', 'spo2', 'glucose', 'fetal_heart_rate'])

/** Keeps a typed value to what the field can hold (a comma becomes the decimal point). */
export function sanitizeVital(key: keyof Vitals, raw: string): string {
  if (key === 'blood_pressure') return raw.replace(/[^\d/]/g, '')
  if (INTEGER_FIELDS.has(key)) return raw.replace(/\D/g, '')
  return raw.replace(',', '.').replace(/[^\d.]/g, '')
}

/** The value as the API takes it: numbers for the integer fields, null to clear. */
export function vitalPayload(key: keyof Vitals, raw: string): string | number | null {
  const value = raw.trim()
  if (!value) return null
  return INTEGER_FIELDS.has(key) ? Number(value) : value
}

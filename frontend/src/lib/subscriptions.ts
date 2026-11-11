import { addMonths, format, parseISO } from 'date-fns'
import type { Tone } from '@/components/ui/badgeTone'
import type { PlanLimits, SubscriptionStatus } from '@/types'

type T = (key: string) => string

export const SUBSCRIPTION_TONE: Record<SubscriptionStatus, Tone> = {
  trial: 'info',
  active: 'ok',
  grace: 'warn',
  read_only: 'danger',
}

/** "79.00" → "$79", "85.50" → "$85.50"; null → null (custom quote). */
export function fmtUsd(amount: string | null): string | null {
  if (amount === null) return null
  const n = Number(amount)
  return `$${Number.isInteger(n) ? n : n.toFixed(2)}`
}

export function limitLabel(t: T, n: number | null, unit = ''): string {
  return n === null ? t('sub.unlimited') : `${n}${unit}`
}

export function expiryLabel(t: T, daysLeft: number | null): string {
  if (daysLeft === null) return t('sub.no_expiry')
  if (daysLeft === 0) return t('sub.expires_today')
  if (daysLeft < 0) return t('sub.expired_ago').replace('{n}', String(-daysLeft))
  return t('sub.days_left').replace('{n}', String(daysLeft))
}

/** One more month of service from the later of the current end and today (manual renewal). */
export function renewOneMonth(periodEnd: string | null, today: string): string {
  const base = periodEnd && periodEnd > today ? periodEnd : today
  return format(addMonths(parseISO(base), 1), 'yyyy-MM-dd')
}

export const LIMIT_KEYS: (keyof PlanLimits)[] = [
  'doctors',
  'support_users',
  'locations',
  'storage_gb',
]

export const LIMIT_LABEL: Record<keyof PlanLimits, string> = {
  doctors: 'sub.col_doctors',
  support_users: 'sub.col_support',
  locations: 'sub.col_locations',
  storage_gb: 'sub.col_storage',
}

/** Text field ↔ limit: empty means null (unlimited / use the plan's). */
export const limitToText = (n: number | null) => (n === null ? '' : String(n))
export const textToLimit = (s: string): number | null => (s.trim() === '' ? null : Number(s))

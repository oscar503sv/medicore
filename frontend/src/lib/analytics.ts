import { addDays, format, parseISO, startOfMonth, subMonths, endOfMonth } from 'date-fns'
import type { AnalyticsParams, AnalyticsTotals } from '@/api/analytics'
import { fmtFee } from '@/lib/fees'

export type Preset = 'week' | 'month' | 'last_month' | 'last_90' | 'range'

const iso = (d: Date) => format(d, 'yyyy-MM-dd')

/** The query a period preset stands for, relative to the clinic's today. */
export function presetParams(preset: Preset, today: string, from?: string, to?: string) {
  const day = parseISO(today)
  switch (preset) {
    case 'week':
    case 'month':
      return { period: preset } satisfies AnalyticsParams
    case 'last_month': {
      const prev = subMonths(day, 1)
      return {
        period: 'range',
        start: iso(startOfMonth(prev)),
        end: iso(endOfMonth(prev)),
      } satisfies AnalyticsParams
    }
    case 'last_90':
      return {
        period: 'range',
        start: iso(addDays(day, -89)),
        end: today,
      } satisfies AnalyticsParams
    case 'range':
      return { period: 'range', start: from, end: to } satisfies AnalyticsParams
  }
}

/** Change in percent between two counts; null without a baseline. */
export function pctChange(current: number, previous: number): number | null {
  if (previous <= 0) return null
  return Math.round(((current - previous) * 100) / previous)
}

/** Change in percentage points between two rates; null when either is missing. */
export function ptsChange(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null) return null
  return Math.round((current - previous) * 10) / 10
}

export function fmtRate(rate: number | null): string {
  return rate === null ? '—' : `${rate}%`
}

/** "$1,234" for big sums, cents kept under $1,000. */
export function fmtIncome(amount: string | number | null | undefined): string {
  if (amount === null || amount === undefined) return '—'
  const n = Number(amount)
  if (n >= 1000) return `$${Math.round(n).toLocaleString('en-US')}`
  return fmtFee(String(n)) ?? '—'
}

export function incomeChange(current: AnalyticsTotals, previous: AnalyticsTotals): number | null {
  if (current.income === null || previous.income === null) return null
  return pctChange(Number(current.income), Number(previous.income))
}

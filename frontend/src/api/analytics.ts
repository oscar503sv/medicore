import { api } from './client'
import type { AnalyticsTier } from '@/types'

export type PeriodKind = 'week' | 'month' | 'range'

export interface AnalyticsTotals {
  booked: number
  attended: number
  no_shows: number
  cancelled: number
  no_show_rate: number | null
  cancellation_rate: number | null
  patients: number
  new_patients: number
  /** Estimated income (USD string); null without the money permission. */
  income: string | null
}

export interface BreakdownRow {
  key: string | null
  label: string | null
  attended: number
  income: string | null
}

export interface AnalyticsOverview {
  tier: AnalyticsTier
  scope: 'own' | 'clinic'
  doctor_id: string | null
  money: boolean
  period: {
    kind: PeriodKind
    start: string
    end: string
    previous_start: string
    previous_end: string
  }
  current: AnalyticsTotals
  previous: AnalyticsTotals
  /** Sections above the clinic's tier come back as null. */
  doctors: { doctor_id: string; name: string; totals: AnalyticsTotals }[] | null
  trend: { week: string; attended: number; income: string | null }[] | null
  types: BreakdownRow[] | null
  insurers: BreakdownRow[] | null
  operations: {
    heatmap: { weekday: number; hour: number; count: number }[]
    lead_times: Record<string, number>
    returning_patients: number
    modules: {
      vaccinations: number | null
      applications: number | null
      procedures: number | null
    }
  } | null
}

export interface AnalyticsParams {
  period: PeriodKind
  start?: string
  end?: string
  doctor_id?: string
}

export const analyticsApi = {
  overview: (params: AnalyticsParams) =>
    api.get<AnalyticsOverview>('/analytics/overview', { params }).then((r) => r.data),
}

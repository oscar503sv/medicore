import { api } from './client'

/** Headline numbers for the home page. A null metric means "no data / no permission". */
export interface DashboardSummary {
  day: string
  appointments_today: number | null
  appointments_delta_pct: number | null
  pending_today: number | null
  patients_total: number | null
  patients_delta_pct: number | null
  occupancy_pct: number | null
  occupancy_delta_pts: number | null
}

export const dashboardApi = {
  summary: () => api.get<DashboardSummary>('/dashboard/summary').then((r) => r.data),
}

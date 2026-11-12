import { api } from './client'
import type { AnalyticsTier } from '@/types'

export type ReportKind =
  | 'appointments'
  | 'income'
  | 'insurers'
  | 'no_shows'
  | 'vaccinations'
  | 'procedures'
  | 'applications'

export type ReportCell = string | number | boolean | null

export interface ReportColumn {
  key: string
  /** text | date | time | money | count | age | bool | enum:<name> */
  kind: string
}

export interface ReportTable {
  columns: ReportColumn[]
  rows: ReportCell[][]
}

export interface Report {
  kind: ReportKind
  start: string
  end: string
  scope: 'own' | 'clinic'
  doctor_id: string | null
  money: boolean
  tier: AnalyticsTier
  summary: ReportTable
  detail: ReportTable
}

export interface ReportParams {
  start: string
  end: string
  doctor_id?: string
}

export const reportsApi = {
  get: (kind: ReportKind, params: ReportParams) =>
    api.get<Report>(`/reports/${kind}`, { params }).then((r) => r.data),

  /** Downloads the CSV (the export is audited server-side). */
  download: async (
    kind: ReportKind,
    params: ReportParams & { part: 'detail' | 'summary'; lang: string },
    filename: string,
  ) => {
    const { data } = await api.get<Blob>(`/reports/${kind}/csv`, {
      params,
      responseType: 'blob',
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}

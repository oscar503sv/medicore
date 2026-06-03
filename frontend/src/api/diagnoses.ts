import { api } from './client'
import type { DiagnosisSuggestion } from '@/types'

export const diagnosesApi = {
  config: () =>
    api.get<{ version: string }>('/diagnoses/config').then((r) => r.data),

  search: (q: string) =>
    api
      .get<DiagnosisSuggestion[]>('/diagnoses/search', { params: { q, limit: 20 } })
      .then((r) => r.data),
}

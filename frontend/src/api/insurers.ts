import { api } from './client'
import type { Insurer } from '@/types'

export interface InsurerPayload {
  name: string
  phone?: string | null
  email?: string | null
  address?: string | null
  contact_person?: string | null
  notes?: string | null
}

export const insurersApi = {
  list: (activeOnly = false) =>
    api
      .get<{ items: Insurer[] }>('/insurers', { params: { active_only: activeOnly } })
      .then((r) => r.data.items),

  create: (payload: InsurerPayload) =>
    api.post<Insurer>('/insurers', payload).then((r) => r.data),

  update: (id: string, payload: Partial<InsurerPayload>) =>
    api.patch<Insurer>(`/insurers/${id}`, payload).then((r) => r.data),

  archive: (id: string) =>
    api.post<Insurer>(`/insurers/${id}/archive`).then((r) => r.data),
}

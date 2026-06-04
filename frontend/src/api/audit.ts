import { api } from './client'
import type { AuditEntry, PaginatedResponse } from '@/types'

export interface AuditListParams {
  action?: string
  category?: string
  entity_type?: string
  actor_id?: string
  date_from?: string
  date_to?: string
  offset?: number
  limit?: number
}

export const auditApi = {
  list: (params: AuditListParams = {}) =>
    api.get<PaginatedResponse<AuditEntry>>('/audit', { params }).then((r) => r.data),
}

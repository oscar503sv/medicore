import { platformApi } from './client'
import type { PaginatedResponse, PlatformAdminProfile, PlatformSession, Tenant } from '@/types'

export interface CreateTenantPayload {
  legal_name: string
  tax_id: string
  slug: string
  timezone?: string
  icd_version?: string
  location_name: string
  admin_name: string
  admin_email: string
  admin_password: string
}

export interface CreateTenantResult {
  tenant: Tenant
  admin_user_id: string
  admin_email: string
}

export const platformAuthApi = {
  login: (email: string, password: string) =>
    platformApi.post<PlatformSession>('/platform/login', { email, password }).then((r) => r.data),

  me: () => platformApi.get<PlatformAdminProfile>('/platform/me').then((r) => r.data),
}

export const platformTenantsApi = {
  list: (params: { status?: string; offset?: number; limit?: number } = {}) =>
    platformApi
      .get<PaginatedResponse<Tenant>>('/platform/tenants', { params })
      .then((r) => r.data),

  get: (id: string) => platformApi.get<Tenant>(`/platform/tenants/${id}`).then((r) => r.data),

  create: (payload: CreateTenantPayload) =>
    platformApi.post<CreateTenantResult>('/platform/tenants', payload).then((r) => r.data),

  update: (
    id: string,
    payload: Partial<{
      legal_name: string
      tax_id: string
      timezone: string
      plan: string
      seat_limit: number
      icd_version: string
    }>,
  ) => platformApi.patch<Tenant>(`/platform/tenants/${id}`, payload).then((r) => r.data),

  setStatus: (id: string, status: string) =>
    platformApi
      .post<Tenant>(`/platform/tenants/${id}/status`, { status })
      .then((r) => r.data),
}

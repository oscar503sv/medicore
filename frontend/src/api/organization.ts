import { api } from './client'
import type { Organization } from '@/types'

export const organizationApi = {
  get: () => api.get<Organization>('/organization').then((r) => r.data),

  update: (payload: Partial<Pick<Organization, 'legal_name' | 'tax_id' | 'timezone' | 'plan'>>) =>
    api.patch<Organization>('/organization', payload).then((r) => r.data),

  addLocation: (payload: { name: string; address?: string; is_primary?: boolean }) =>
    api.post<Organization>('/organization/locations', payload).then((r) => r.data),

  updateLocation: (id: string, payload: { name?: string; address?: string }) =>
    api.patch<Organization>(`/organization/locations/${id}`, payload).then((r) => r.data),
}

import { api } from './client'
import type { Organization, PrintSettings, Subscription, SubscriptionPayment } from '@/types'

export const organizationApi = {
  get: () => api.get<Organization>('/organization').then((r) => r.data),

  subscription: () => api.get<Subscription>('/organization/subscription').then((r) => r.data),

  payments: () =>
    api.get<SubscriptionPayment[]>('/organization/subscription/payments').then((r) => r.data),

  update: (payload: Partial<Pick<Organization, 'legal_name' | 'tax_id'>>) =>
    api.patch<Organization>('/organization', payload).then((r) => r.data),

  addLocation: (payload: {
    name: string
    address?: string
    phone?: string
    is_primary?: boolean
  }) =>
    api.post<Organization>('/organization/locations', payload).then((r) => r.data),

  updateLocation: (id: string, payload: { name?: string; address?: string; phone?: string }) =>
    api.patch<Organization>(`/organization/locations/${id}`, payload).then((r) => r.data),

  setPrintSettings: (payload: PrintSettings) =>
    api.put<Organization>('/organization/print-settings', payload).then((r) => r.data),
}

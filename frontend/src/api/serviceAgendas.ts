import { api } from './client'

export type ServiceAgendaKind = 'vaccination'

export interface ServiceAgenda {
  id: string
  name: string
  kind: ServiceAgendaKind
  location_id: string | null
  active: boolean
  /** Booking duration of the agenda's rules (null → not configured yet). */
  slot_minutes: number | null
  created_at: string
  updated_at: string
}

export interface CreateServiceAgendaPayload {
  name: string
  kind: ServiceAgendaKind
  location_id?: string | null
}

/** Only the fields present change; location_id null clears the location. */
export interface UpdateServiceAgendaPayload {
  name?: string
  location_id?: string | null
}

export const serviceAgendasApi = {
  list: (activeOnly = false) =>
    api
      .get<ServiceAgenda[]>('/service-agendas', { params: { active_only: activeOnly } })
      .then((r) => r.data),

  create: (payload: CreateServiceAgendaPayload) =>
    api.post<ServiceAgenda>('/service-agendas', payload).then((r) => r.data),

  update: (id: string, payload: UpdateServiceAgendaPayload) =>
    api.patch<ServiceAgenda>(`/service-agendas/${id}`, payload).then((r) => r.data),

  setActive: (id: string, active: boolean) =>
    api.post<ServiceAgenda>(`/service-agendas/${id}/active`, { active }).then((r) => r.data),
}

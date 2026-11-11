import { api } from './client'
import type { AppointmentType } from '@/types'

/** A doctor's price per appointment type ("25.00", USD); a type without a price is absent. */
export interface DoctorFees {
  doctor_id: string
  doctor_name: string
  prices: Partial<Record<AppointmentType, string>>
  /** The current user may change them. */
  editable: boolean
}

/** Appointment types priced per doctor (procedures come from the procedure catalog). */
export const PRICED_TYPES: AppointmentType[] = ['consult', 'follow_up', 'check_up', 'emergency']

export const feesApi = {
  list: () => api.get<DoctorFees[]>('/fees').then((r) => r.data),

  update: (doctorId: string, prices: Partial<Record<AppointmentType, string>>) =>
    api.put<DoctorFees>(`/fees/${doctorId}`, { prices }).then((r) => r.data),
}

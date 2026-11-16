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

export const feesApi = {
  list: () => api.get<DoctorFees[]>('/fees').then((r) => r.data),

  update: (doctorId: string, prices: Partial<Record<AppointmentType, string>>) =>
    api.put<DoctorFees>(`/fees/${doctorId}`, { prices }).then((r) => r.data),
}

/** A vaccine's price at the clinic; `price` is null when it has none. */
export interface VaccinePrice {
  vaccine_code: string
  in_schedule: boolean
  price: string | null
  updated_at: string | null
}

export interface VaccinePriceList {
  /** The current user may change the prices (fees.manage_all). */
  editable: boolean
  items: VaccinePrice[]
}

export const vaccinePricesApi = {
  list: () => api.get<VaccinePriceList>('/fees/vaccines').then((r) => r.data),

  /** A null price removes it; $0 is a valid price (the clinic gives that vaccine away). */
  set: (vaccineCode: string, price: string | null) =>
    api.put<VaccinePrice>(`/fees/vaccines/${encodeURIComponent(vaccineCode)}`, { price }).then((r) => r.data),
}

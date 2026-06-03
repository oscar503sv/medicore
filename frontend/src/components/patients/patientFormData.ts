import type { Patient } from '@/types'

export interface PatientFormState {
  first_name: string
  last_name: string
  sex: string
  date_of_birth: string
  blood_type: string
  primary_doctor_id: string
  phone: string
  email: string
  address: string
  emergency_contact_name: string
  emergency_contact_phone: string
  tags: string[]
  allergies: string[]
}

export function emptyPatientForm(): PatientFormState {
  return {
    first_name: '',
    last_name: '',
    sex: 'female',
    date_of_birth: '',
    blood_type: '',
    primary_doctor_id: '',
    phone: '',
    email: '',
    address: '',
    emergency_contact_name: '',
    emergency_contact_phone: '',
    tags: [],
    allergies: [],
  }
}

export function patientToForm(p: Patient): PatientFormState {
  return {
    first_name: p.first_name,
    last_name: p.last_name,
    sex: p.sex,
    date_of_birth: p.date_of_birth,
    blood_type: p.blood_type ?? '',
    primary_doctor_id: p.primary_doctor_id ?? '',
    phone: p.contact.phone ?? '',
    email: p.contact.email ?? '',
    address: p.contact.address ?? '',
    emergency_contact_name: p.contact.emergency_contact_name ?? '',
    emergency_contact_phone: p.contact.emergency_contact_phone ?? '',
    tags: [...p.tags],
    allergies: [...p.allergies],
  }
}

/** Map the flat form state to the patient create/update payload shape. */
export function formToPayload(f: PatientFormState) {
  return {
    first_name: f.first_name,
    last_name: f.last_name,
    sex: f.sex,
    date_of_birth: f.date_of_birth,
    blood_type: f.blood_type || null,
    primary_doctor_id: f.primary_doctor_id || null,
    tags: f.tags,
    allergies: f.allergies,
    contact: {
      phone: f.phone || null,
      email: f.email || null,
      address: f.address || null,
      emergency_contact_name: f.emergency_contact_name || null,
      emergency_contact_phone: f.emergency_contact_phone || null,
    },
  }
}

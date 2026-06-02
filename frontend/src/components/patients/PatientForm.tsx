import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { Input, Select } from '@/components/ui/Input'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import type { Patient } from '@/types'

const BLOOD_TYPES = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']

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

export function PatientForm({
  value,
  onChange,
}: {
  value: PatientFormState
  onChange: (next: PatientFormState) => void
}) {
  const t = useT()
  const set = (patch: Partial<PatientFormState>) => onChange({ ...value, ...patch })

  // Doctors come from the booking-options endpoint (admin/doctor/receptionist). If the caller
  // can't access it, the select simply stays empty — primary doctor is optional.
  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
  })

  return (
    <div className="space-y-5">
      <Section title={t('patientform.personal')}>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('patientform.first_name')}
            value={value.first_name}
            onChange={(e) => set({ first_name: e.target.value })}
            required
          />
          <Input
            label={t('patientform.last_name')}
            value={value.last_name}
            onChange={(e) => set({ last_name: e.target.value })}
            required
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Select label={t('patientform.sex')} value={value.sex} onChange={(e) => set({ sex: e.target.value })}>
            <option value="female">{t('sex.female')}</option>
            <option value="male">{t('sex.male')}</option>
            <option value="other">{t('sex.other')}</option>
          </Select>
          <Input
            label={t('patientform.dob')}
            type="date"
            value={value.date_of_birth}
            onChange={(e) => set({ date_of_birth: e.target.value })}
            required
          />
        </div>
      </Section>

      <Section title={t('patientform.contact')}>
        <div className="grid grid-cols-2 gap-4">
          <Input label={t('patientform.phone')} value={value.phone} onChange={(e) => set({ phone: e.target.value })} />
          <Input label={t('patientform.email')} type="email" value={value.email} onChange={(e) => set({ email: e.target.value })} />
        </div>
        <Input label={t('patientform.address')} value={value.address} onChange={(e) => set({ address: e.target.value })} />
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('patientform.emergency_name')}
            value={value.emergency_contact_name}
            onChange={(e) => set({ emergency_contact_name: e.target.value })}
          />
          <Input
            label={t('patientform.emergency_phone')}
            value={value.emergency_contact_phone}
            onChange={(e) => set({ emergency_contact_phone: e.target.value })}
          />
        </div>
      </Section>

      <Section title={t('patientform.clinical')}>
        <div className="grid grid-cols-2 gap-4">
          <Select
            label={t('patientform.blood_type')}
            value={value.blood_type}
            onChange={(e) => set({ blood_type: e.target.value })}
          >
            <option value="">—</option>
            {BLOOD_TYPES.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </Select>
        </div>
        <ChipInput
          label={t('patientform.allergies')}
          placeholder={t('patientform.allergies_ph')}
          values={value.allergies}
          onChange={(allergies) => set({ allergies })}
          tone="danger"
        />
        <ChipInput
          label={t('patientform.tags')}
          placeholder={t('patientform.tags_ph')}
          values={value.tags}
          onChange={(tags) => set({ tags })}
          tone="accent"
        />
      </Section>

      <Section title={t('patientform.admin')}>
        <Select
          label={t('patientform.doctor')}
          value={value.primary_doctor_id}
          onChange={(e) => set({ primary_doctor_id: e.target.value })}
        >
          <option value="">—</option>
          {options?.doctors.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <p className="eyebrow">{title}</p>
      {children}
    </div>
  )
}

function ChipInput({
  label,
  placeholder,
  values,
  onChange,
  tone,
}: {
  label: string
  placeholder: string
  values: string[]
  onChange: (next: string[]) => void
  tone: 'danger' | 'accent'
}) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const v = draft.trim()
    if (v && !values.includes(v)) onChange([...values, v])
    setDraft('')
  }
  return (
    <div>
      <label className="eyebrow mb-1 block">{label}</label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-line bg-bg p-1.5">
        {values.map((v) => (
          <span
            key={v}
            className={cn(
              'inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-xs',
              tone === 'danger' ? 'bg-[var(--danger-10)] text-danger' : 'bg-[var(--accent-10)] text-accent',
            )}
          >
            {v}
            <button type="button" onClick={() => onChange(values.filter((x) => x !== v))}>
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          onBlur={add}
          placeholder={placeholder}
          className="min-w-[8rem] flex-1 bg-transparent px-1 text-sm text-tx placeholder:text-tx-4 focus:outline-none"
        />
      </div>
    </div>
  )
}

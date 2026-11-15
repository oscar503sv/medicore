import { Select } from '@/components/ui/Input'
import {
  APPOINTMENT_TYPES,
  isAppointmentType,
  typeHintKey,
  typeLabelKey,
} from '@/lib/appointmentTypes'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { AppointmentType } from '@/types'

/** Appointment type with its hint; procedures only for clinics that have the module. */
export function AppointmentTypeSelect({
  value,
  onChange,
}: {
  value: AppointmentType
  onChange: (type: AppointmentType) => void
}) {
  const t = useT()
  const canProcedures = useAuthStore((s) => s.can('procedures.view'))
  return (
    <Select
      label={t('appt.type')}
      value={value}
      hint={t(typeHintKey(value))}
      onChange={(e) => {
        if (isAppointmentType(e.target.value)) onChange(e.target.value)
      }}
    >
      {APPOINTMENT_TYPES.filter((type) => type !== 'procedure' || canProcedures).map((type) => (
        <option key={type} value={type}>
          {t(typeLabelKey(type))}
        </option>
      ))}
    </Select>
  )
}

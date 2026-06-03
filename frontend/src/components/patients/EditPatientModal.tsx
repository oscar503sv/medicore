import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { PatientForm } from '@/components/patients/PatientForm'
import {
  formToPayload,
  patientToForm,
  type PatientFormState,
} from '@/components/patients/patientFormData'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Patient } from '@/types'

export function EditPatientModal({
  patient,
  onClose,
}: {
  patient: Patient | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState<PatientFormState | null>(null)

  // Load the patient's current values into the form whenever a new target opens.
  useEffect(() => {
    setForm(patient ? patientToForm(patient) : null)
  }, [patient])

  const mutation = useMutation({
    mutationFn: () => patientsApi.update(patient!.id, formToPayload(form!)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patients'] })
      qc.invalidateQueries({ queryKey: ['patient', patient!.id] })
      toast(t('patients.updated_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={!!patient} onClose={onClose} title={t('patients.edit')} width="max-w-2xl">
      {form && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            mutation.mutate()
          }}
          className="space-y-5 p-5"
        >
          <PatientForm value={form} onChange={setForm} />
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button
              type="submit"
              loading={mutation.isPending}
              disabled={!form.first_name || !form.last_name || !form.date_of_birth}
            >
              {t('app.save')}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

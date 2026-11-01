import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { PatientForm } from '@/components/patients/PatientForm'
import {
  emptyPatientForm,
  formToPayload,
  hasPatientFormErrors,
  type PatientFormState,
} from '@/components/patients/patientFormData'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Patient } from '@/types'

export function NewPatientModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  /** Called with the new patient (e.g. to select it in the form that opened this modal). */
  onCreated?: (patient: Patient) => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState<PatientFormState>(emptyPatientForm)

  const mutation = useMutation({
    mutationFn: () => patientsApi.create(formToPayload(form)),
    onSuccess: (patient) => {
      qc.invalidateQueries({ queryKey: ['patients'] })
      onCreated?.(patient)
      toast(t('patients.created_ok'))
      setForm(emptyPatientForm())
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('patients.new')} width="max-w-2xl">
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
            disabled={
              !form.first_name || !form.last_name || !form.date_of_birth || hasPatientFormErrors(form)
            }
          >
            {t('app.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { PatientForm } from '@/components/patients/PatientForm'
import {
  emptyPatientForm,
  formToPayload,
  type PatientFormState,
} from '@/components/patients/patientFormData'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'

export function NewPatientModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState<PatientFormState>(emptyPatientForm)

  const mutation = useMutation({
    mutationFn: () => patientsApi.create(formToPayload(form)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patients'] })
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
            disabled={!form.first_name || !form.last_name || !form.date_of_birth}
          >
            {t('app.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

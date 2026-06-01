import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'

export function NewPatientModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    sex: 'female',
    date_of_birth: '',
  })

  const mutation = useMutation({
    mutationFn: () => patientsApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patients'] })
      toast('Paciente registrado')
      onClose()
      setForm({ first_name: '', last_name: '', sex: 'female', date_of_birth: '' })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('patients.new')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
        className="space-y-4 p-5"
      >
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Nombre"
            value={form.first_name}
            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            required
          />
          <Input
            label="Apellidos"
            value={form.last_name}
            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            required
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Select
            label="Sexo"
            value={form.sex}
            onChange={(e) => setForm({ ...form, sex: e.target.value })}
          >
            <option value="female">Femenino</option>
            <option value="male">Masculino</option>
            <option value="other">Otro</option>
          </Select>
          <Input
            label="Fecha de nacimiento"
            type="date"
            value={form.date_of_birth}
            onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })}
            required
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {t('app.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { proceduresApi } from '@/api/procedures'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { usePerformer } from '@/lib/procedures'

export interface PickedPatient {
  id: string
  name: string
  code: string
  allergies: string[]
}

export interface ProcedureAppointment {
  id: string
  /** Naive clinic wall-clock. */
  start: string
  reason: string
}

/**
 * Register a procedure directly (not ordered in a consultation): the patient, a catalog
 * procedure this user may perform and the indication; optionally tied to a procedure
 * appointment. Opens the procedure on success.
 */
export function NewProcedureModal({
  open,
  onClose,
  patient: preset,
  appointment,
}: {
  open: boolean
  onClose: () => void
  patient?: PickedPatient | null
  appointment?: ProcedureAppointment | null
}) {
  const t = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const performer = usePerformer()
  const [patient, setPatient] = useState<PickedPatient | null>(null)
  const [search, setSearch] = useState('')
  const [typeId, setTypeId] = useState('')
  const [indication, setIndication] = useState('')

  useEffect(() => {
    if (!open) return
    setPatient(preset ?? null)
    setSearch('')
    setTypeId('')
    setIndication(appointment?.reason ?? '')
  }, [open, preset, appointment])

  const { data: catalog } = useQuery({
    queryKey: ['procedure-catalog'],
    queryFn: proceduresApi.catalog,
    enabled: open,
  })
  const { data: patients } = useQuery({
    queryKey: ['patients', { q: search, status: 'active', limit: 6 }],
    queryFn: () => patientsApi.list({ q: search || undefined, status: 'active', limit: 6 }),
    enabled: open && !patient,
  })

  const types = performer.types(catalog ?? [])
  const create = useMutation({
    mutationFn: () =>
      proceduresApi.create({
        patient_id: patient!.id,
        type_id: typeId,
        indication: indication.trim(),
        appointment_id: appointment?.id ?? null,
      }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['procedures-worklist'] })
      qc.invalidateQueries({ queryKey: ['procedures-patient', d.patient.id] })
      qc.setQueryData(['procedure', d.procedure.id], d)
      onClose()
      navigate(`/procedures/${d.procedure.id}`)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('prc.new_title')} width="max-w-xl">
      <form
        className="space-y-5 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        {appointment && (
          <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-tx-2">
            {t('prc.for_appointment')
              .replace('{time}', fmtTime(appointment.start))
              .replace('{reason}', appointment.reason)}
          </p>
        )}

        <div>
          <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{t('prc.patient')}</span>
          {patient ? (
            <div className="flex items-center justify-between rounded-lg border border-accent bg-[var(--accent-10)] px-3 py-2.5">
              <div>
                <p className="text-sm font-medium text-tx">{patient.name}</p>
                <p className="font-mono text-xs text-tx-3">{patient.code}</p>
                {patient.allergies.length > 0 && (
                  <p className="mt-0.5 flex items-center gap-1 text-xs text-danger">
                    <AlertTriangle className="h-3 w-3" />
                    {patient.allergies.join(', ')}
                  </p>
                )}
              </div>
              {!preset && (
                <Button type="button" size="sm" variant="ghost" onClick={() => setPatient(null)}>
                  {t('prc.change_patient')}
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <Input
                placeholder={t('prc.patient_search')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoFocus
              />
              <div className="max-h-52 space-y-1 overflow-y-auto">
                {patients?.items.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() =>
                      setPatient({
                        id: p.id,
                        name: `${p.first_name} ${p.last_name}`,
                        code: p.code,
                        allergies: p.allergies,
                      })
                    }
                    className="flex w-full items-center justify-between rounded-lg border border-line px-3 py-2 text-left transition-colors hover:bg-surface-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-tx">
                        {p.first_name} {p.last_name}
                      </p>
                      <p className="font-mono text-xs text-tx-3">{p.code}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div>
          <Select label={t('prc.type')} value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            <option value="">{t('prc.type_ph')}</option>
            {types.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </Select>
          {!performer.isDoctor && (
            <p className="mt-1.5 text-xs text-tx-3">{t('prc.nurse_scope')}</p>
          )}
        </div>

        <Textarea
          label={t('prc.indication')}
          rows={2}
          value={indication}
          placeholder={t('prc.indication_ph')}
          onChange={(e) => setIndication(e.target.value)}
          required
        />

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button
            type="submit"
            variant="accent"
            loading={create.isPending}
            disabled={!patient || !typeId || !indication.trim()}
          >
            {t('prc.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

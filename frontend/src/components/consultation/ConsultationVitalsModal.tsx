import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { unitLabel } from '@/components/patients/vitalsData'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { fmtDateTime, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Appointment, Vitals } from '@/types'
import { sanitizeVital, VITAL_FIELDS, vitalPayload } from './vitalFields'

/**
 * Nursing's way into a confirmed or open appointment: the patient header and the vitals,
 * nothing of the note. Before the consultation starts they are kept for the doctor. Only the fields that were edited are sent, so it never overwrites what the
 * doctor typed in the meantime.
 */
export function ConsultationVitalsModal({
  appointment,
  onClose,
}: {
  appointment: Appointment | null
  onClose: () => void
}) {
  const t = useT()
  return (
    <Modal
      open={!!appointment}
      onClose={onClose}
      title={t('consult.vitals_title')}
      width="max-w-xl"
    >
      {appointment && (
        <VitalsForm key={appointment.id} appointment={appointment} onClose={onClose} />
      )}
    </Modal>
  )
}

function VitalsForm({ appointment, onClose }: { appointment: Appointment; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const formId = useId()
  const errorId = useId()
  // Only what the user typed; everything else shows the stored value.
  const [edits, setEdits] = useState<Partial<Record<keyof Vitals, string>>>({})

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['consultation-vitals', appointment.id],
    queryFn: () => appointmentsApi.vitals(appointment.id),
    retry: false,
  })

  const save = useMutation({
    mutationFn: (changes: Partial<Vitals>) => appointmentsApi.updateVitals(appointment.id, changes),
    onSuccess: (view) => {
      qc.setQueryData(['consultation-vitals', appointment.id], view)
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(t('consult.vitals_saved'))
      onClose()
    },
  })

  const stored = (key: keyof Vitals) => (data?.vitals[key] == null ? '' : String(data.vitals[key]))
  const shown = (key: keyof Vitals) => edits[key] ?? stored(key)
  const changes = Object.fromEntries(
    VITAL_FIELDS.filter((f) => edits[f.key] !== undefined && edits[f.key] !== stored(f.key)).map(
      (f) => [f.key, vitalPayload(f.key, edits[f.key]!)],
    ),
  ) as Partial<Vitals>
  const isDirty = Object.keys(changes).length > 0

  if (isLoading) {
    return (
      <div role="status" className="flex items-center justify-center gap-2 p-10 text-sm text-tx-3">
        <Spinner />
        {t('consult.vitals_loading')}
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="space-y-4 p-5">
        <p role="alert" className="text-sm text-danger">
          {errorMessage(error, t('consult.vitals_error'))}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('app.close')}
          </Button>
          <Button variant="subtle" onClick={() => void refetch()}>
            {t('consult.vitals_retry')}
          </Button>
        </div>
      </div>
    )
  }

  const patient = data.patient
  const empty = Object.values(data.vitals).every((v) => v === null || v === '')

  return (
    <form
      id={formId}
      className="space-y-4 p-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (isDirty) save.mutate(changes)
      }}
    >
      <header className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
        <p className="font-medium text-tx">
          {patient
            ? `${patient.first_name} ${patient.last_name}`
            : (appointment.patient_name ?? '—')}
          {patient && <span className="ml-2 font-mono text-xs text-tx-3">{patient.code}</span>}
        </p>
        <p className="text-tx-3">
          {fmtTime(appointment.scheduled_start)}
          {data.doctor_name && (
            <> · {t('consult.vitals_doctor').replace('{name}', data.doctor_name)}</>
          )}
        </p>
        {patient && (
          <p className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-tx-3">{t('consult.allergies')}:</span>
            {patient.allergies.length > 0 ? (
              patient.allergies.map((a) => (
                <Badge key={a} tone="danger">
                  {a}
                </Badge>
              ))
            ) : (
              <span className="text-xs text-tx-3">{t('consult.no_allergies')}</span>
            )}
          </p>
        )}
      </header>

      <p className="text-xs text-tx-3">
        {empty ? t('consult.vitals_none') : t('consult.vitals_hint')}
        {data.last_saved_at && (
          <>
            {' '}
            · {t('consult.vitals_last_saved').replace('{time}', fmtDateTime(data.last_saved_at))}
          </>
        )}
      </p>

      {data.phase === 'triage' && (
        <p className="rounded-lg bg-surface-2/60 p-2 text-xs text-tx-3">
          {t('consult.vitals_pre_hint')}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {VITAL_FIELDS.map((f) => {
          const inputId = `${formId}-${f.key}`
          return (
            <div
              key={f.key}
              className="rounded-lg border border-line bg-surface p-3 focus-within:border-accent"
            >
              <label htmlFor={inputId} className="eyebrow mb-1 block">
                {t(f.labelKey)}
              </label>
              <div className="flex items-baseline gap-1.5">
                <input
                  id={inputId}
                  value={shown(f.key)}
                  onChange={(e) =>
                    setEdits((p) => ({ ...p, [f.key]: sanitizeVital(f.key, e.target.value) }))
                  }
                  placeholder={f.placeholder}
                  inputMode={f.key === 'blood_pressure' ? 'text' : 'decimal'}
                  aria-describedby={save.isError ? errorId : undefined}
                  className="w-full min-w-0 bg-transparent font-serif text-2xl text-tx placeholder:text-tx-4 focus:outline-none"
                />
                <span className="shrink-0 text-xs text-tx-3">{unitLabel(t, f.unit)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {save.isError && (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {errorMessage(save.error)}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          {t('consult.vitals_cancel')}
        </Button>
        <Button type="submit" loading={save.isPending} disabled={!isDirty}>
          {t('consult.vitals_save')}
        </Button>
      </div>
    </form>
  )
}

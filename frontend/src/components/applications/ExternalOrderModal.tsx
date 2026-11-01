import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, UserPlus } from 'lucide-react'
import { errorMessage } from '@/api/client'
import {
  applicationsApi,
  DEFAULT_OBSERVATION_MINUTES,
  ROUTES,
  type ApplicationRoute,
} from '@/api/applications'
import { patientsApi } from '@/api/patients'
import { NewPatientModal } from '@/components/patients/NewPatientModal'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Patient } from '@/types'

const EMPTY = {
  drug: '',
  dose: '',
  route: 'im' as ApplicationRoute,
  doses: '1',
  interval: '24',
  observation: String(DEFAULT_OBSERVATION_MINUTES),
  instructions: '',
  prescriber: '',
  jvpm: '',
}

/**
 * Walk-in application from an outside prescription: pick (or register) the patient, then
 * what to apply and who prescribed it (name + JVPM). No file is uploaded.
 */
export function ExternalOrderModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const [patient, setPatient] = useState<Patient | null>(null)
  const [search, setSearch] = useState('')
  const [newPatient, setNewPatient] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const set = (patch: Partial<typeof EMPTY>) => setForm((f) => ({ ...f, ...patch }))

  useEffect(() => {
    if (!open) return
    setPatient(null)
    setSearch('')
    setForm(EMPTY)
  }, [open])

  const { data: patients } = useQuery({
    queryKey: ['patients', { q: search, status: 'active', limit: 6 }],
    queryFn: () => patientsApi.list({ q: search || undefined, status: 'active', limit: 6 }),
    enabled: open && !patient,
  })

  const multi = Number(form.doses) > 1
  const create = useMutation({
    mutationFn: () =>
      applicationsApi.createExternal({
        patient_id: patient!.id,
        drug: form.drug.trim(),
        dose: form.dose.trim(),
        route: form.route,
        prescriber: form.prescriber.trim(),
        jvpm: form.jvpm.trim(),
        doses_total: Number(form.doses) || 1,
        interval_hours: multi ? Number(form.interval) || null : null,
        observation_minutes: Number(form.observation) || 0,
        instructions: form.instructions.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['applications-worklist'] })
      qc.invalidateQueries({ queryKey: ['applications-patient', patient!.id] })
      toast(t('apl.order_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const ready =
    patient && form.drug.trim() && form.dose.trim() && form.prescriber.trim() && form.jvpm.trim()

  return (
    <>
      <Modal
        open={open && !newPatient}
        onClose={onClose}
        title={t('apl.walk_in_title')}
        width="max-w-2xl"
      >
        <form
          className="space-y-5 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate()
          }}
        >
          {/* Patient */}
          <div>
            <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
              {t('apl.patient')}
            </span>
            {patient ? (
              <div className="flex items-center justify-between rounded-lg border border-accent bg-[var(--accent-10)] px-3 py-2.5">
                <div>
                  <p className="text-sm font-medium text-tx">
                    {patient.first_name} {patient.last_name}
                  </p>
                  <p className="font-mono text-xs text-tx-3">{patient.code}</p>
                  {patient.allergies.length > 0 && (
                    <p className="mt-0.5 flex items-center gap-1 text-xs text-danger">
                      <AlertTriangle className="h-3 w-3" />
                      {patient.allergies.join(', ')}
                    </p>
                  )}
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => setPatient(null)}>
                  {t('apl.change_patient')}
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <div className="flex-1">
                    <Input
                      placeholder={t('apl.patient_search')}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <Button type="button" variant="outline" onClick={() => setNewPatient(true)}>
                    <UserPlus className="h-4 w-4" />
                    {t('apl.new_patient')}
                  </Button>
                </div>
                <div className="max-h-52 space-y-1 overflow-y-auto">
                  {patients?.items.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setPatient(p)}
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

          {/* What to apply */}
          <div className="grid gap-4 sm:grid-cols-[1.4fr_1fr_1fr]">
            <Input
              label={t('apl.drug')}
              value={form.drug}
              placeholder={t('apl.drug_ph')}
              onChange={(e) => set({ drug: e.target.value })}
              required
            />
            <Input
              label={t('apl.dose')}
              value={form.dose}
              placeholder={t('apl.dose_ph')}
              onChange={(e) => set({ dose: e.target.value })}
              required
            />
            <Select
              label={t('apl.route')}
              value={form.route}
              onChange={(e) => set({ route: e.target.value as ApplicationRoute })}
            >
              {ROUTES.map((r) => (
                <option key={r} value={r}>
                  {t(`apl.route.${r}`)}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Input
              type="number"
              min={1}
              max={30}
              label={t('apl.doses_total')}
              value={form.doses}
              onChange={(e) => set({ doses: e.target.value })}
            />
            <Input
              type="number"
              min={1}
              max={168}
              label={t('apl.interval')}
              value={multi ? form.interval : ''}
              disabled={!multi}
              onChange={(e) => set({ interval: e.target.value })}
            />
            <Input
              type="number"
              min={0}
              max={240}
              label={t('apl.observation')}
              value={form.observation}
              onChange={(e) => set({ observation: e.target.value })}
            />
          </div>
          <Textarea
            label={t('apl.instructions')}
            rows={2}
            value={form.instructions}
            onChange={(e) => set({ instructions: e.target.value })}
          />

          {/* Who prescribed it */}
          <div className="rounded-lg border border-line bg-surface-2/40 p-4">
            <div className="grid gap-4 sm:grid-cols-[1.6fr_1fr]">
              <Input
                label={t('apl.prescriber')}
                value={form.prescriber}
                placeholder={t('apl.prescriber_ph')}
                onChange={(e) => set({ prescriber: e.target.value })}
                required
              />
              <Input
                label={t('apl.jvpm')}
                value={form.jvpm}
                inputMode="numeric"
                placeholder="12345"
                onChange={(e) => set({ jvpm: e.target.value.replace(/\D/g, '').slice(0, 6) })}
                className="font-mono"
                required
              />
            </div>
            <p className="mt-2 text-xs text-tx-3">{t('apl.jvpm_hint')}</p>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" variant="accent" loading={create.isPending} disabled={!ready}>
              {t('apl.create_order')}
            </Button>
          </div>
        </form>
      </Modal>
      <NewPatientModal
        open={newPatient}
        onClose={() => setNewPatient(false)}
        onCreated={(p) => setPatient(p)}
      />
    </>
  )
}

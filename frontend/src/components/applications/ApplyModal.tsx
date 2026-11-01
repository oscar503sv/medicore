import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Timer } from 'lucide-react'
import { errorMessage } from '@/api/client'
import {
  applicationsApi,
  SITES,
  type ApplicationOrder,
  type ApplicationOutcome,
  type ApplicationSite,
} from '@/api/applications'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Segmented } from '@/components/ui/Segmented'
import { toast } from '@/components/ui/Toast'
import { originLabel } from '@/lib/applications'
import { useT } from '@/lib/i18n'

export interface ApplyTarget {
  order: ApplicationOrder
  patientName: string
}

/**
 * Record the order's next dose. When the drug clashes with the patient's allergies the nurse
 * must write why it is applied anyway (the backend enforces it too).
 */
export function ApplyModal({
  target,
  onClose,
}: {
  target: ApplyTarget | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [outcome, setOutcome] = useState<ApplicationOutcome>('applied')
  const [lot, setLot] = useState('')
  const [expiry, setExpiry] = useState('')
  const [site, setSite] = useState<ApplicationSite | ''>('')
  const [bp, setBp] = useState('')
  const [temp, setTemp] = useState('')
  const [override, setOverride] = useState('')
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (!target) return
    setOutcome('applied')
    setLot('')
    setExpiry('')
    setSite('')
    setBp('')
    setTemp('')
    setOverride('')
    setNotes('')
  }, [target])

  const order = target?.order
  const applied = outcome === 'applied'
  const clashes = order?.allergy_conflicts ?? []
  const needsOverride = applied && clashes.length > 0
  const injectable = order && ['im', 'iv', 'sc', 'id'].includes(order.route)

  const save = useMutation({
    mutationFn: () =>
      applicationsApi.record(order!.id, {
        outcome,
        lot: applied ? lot.trim() || null : null,
        lot_expiry: applied ? expiry || null : null,
        site: applied ? site || null : null,
        blood_pressure: bp.trim() || null,
        temperature: temp ? Number(temp) : null,
        allergy_override: needsOverride ? override.trim() : null,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['applications-worklist'] })
      qc.invalidateQueries({ queryKey: ['applications-patient', order!.patient_id] })
      toast(t('apl.apply_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={target !== null} onClose={onClose} title={t('apl.apply_title')} width="max-w-xl">
      {order && target && (
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          {/* What is being applied */}
          <div className="rounded-lg border border-line bg-surface-2/40 p-3">
            <p className="text-sm font-medium text-tx">
              {order.drug} {order.dose} · {t(`apl.route_short.${order.route}`)}
            </p>
            <p className="mt-0.5 text-xs text-tx-3">
              {target.patientName} ·{' '}
              {t('apl.dose_of')
                .replace('{n}', String(order.next_dose ?? 1))
                .replace('{total}', String(order.doses_total))}{' '}
              · {originLabel(t, order)}
            </p>
            {order.instructions && <p className="mt-1 text-xs text-tx-2">{order.instructions}</p>}
          </div>

          <div>
            <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
              {t('apl.outcome')}
            </span>
            <Segmented<ApplicationOutcome>
              value={outcome}
              onChange={setOutcome}
              options={(['applied', 'refused', 'contraindicated'] as const).map((o) => ({
                value: o,
                label: t(`apl.outcome.${o}`),
              }))}
            />
          </div>

          {needsOverride && (
            <div className="space-y-2 rounded-lg border border-[var(--danger-10)] bg-[var(--danger-10)] p-3">
              <p className="flex items-center gap-2 text-sm font-medium text-danger">
                <AlertTriangle className="h-4 w-4" />
                {t('apl.allergy_title')}
              </p>
              <p className="text-xs text-tx-2">
                {t('apl.allergy_desc')
                  .replace('{list}', clashes.join(', '))
                  .replace('{drug}', order.drug)}
              </p>
              <Input
                label={t('apl.allergy_reason')}
                value={override}
                placeholder={t('apl.allergy_reason_ph')}
                onChange={(e) => setOverride(e.target.value)}
                required
              />
            </div>
          )}

          {applied && (
            <div className="grid gap-4 sm:grid-cols-3">
              <Input
                label={t('apl.lot')}
                value={lot}
                placeholder={t('apl.lot_ph')}
                onChange={(e) => setLot(e.target.value)}
                className="font-mono"
              />
              <Input
                type="date"
                label={t('apl.lot_expiry')}
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              />
              <Select
                label={t('apl.site')}
                value={site}
                onChange={(e) => setSite(e.target.value as ApplicationSite | '')}
                disabled={!injectable}
              >
                <option value="">{t('apl.site_none')}</option>
                {SITES.map((s) => (
                  <option key={s} value={s}>
                    {t(`apl.site.${s}`)}
                  </option>
                ))}
              </Select>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t('apl.bp')}
              value={bp}
              placeholder="120/80"
              onChange={(e) => setBp(e.target.value)}
            />
            <Input
              type="number"
              step="0.1"
              min={30}
              max={45}
              label={t('apl.temp')}
              value={temp}
              placeholder="36.5"
              onChange={(e) => setTemp(e.target.value)}
            />
          </div>

          <Textarea
            label={t('apl.notes')}
            rows={2}
            value={notes}
            placeholder={t('apl.notes_ph')}
            onChange={(e) => setNotes(e.target.value)}
          />

          {applied && order.observation_minutes > 0 && (
            <p className="flex items-center gap-2 text-xs text-tx-3">
              <Timer className="h-3.5 w-3.5" />
              {t('apl.observation_after').replace('{n}', String(order.observation_minutes))}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button
              type="submit"
              variant="accent"
              loading={save.isPending}
              disabled={needsOverride && !override.trim()}
            >
              {t('apl.apply_title')}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

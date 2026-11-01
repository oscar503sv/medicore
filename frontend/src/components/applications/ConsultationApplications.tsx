import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Syringe, Trash2 } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { consultationsApi } from '@/api/consultations'
import { DEFAULT_OBSERVATION_MINUTES, ROUTES, type ApplicationRoute } from '@/api/applications'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Input'
import { toast } from '@/components/ui/Toast'
import { planLabel } from '@/lib/applications'
import { useT } from '@/lib/i18n'
import type { Consultation } from '@/types'

const EMPTY = {
  drug: '',
  dose: '',
  route: 'im' as ApplicationRoute,
  doses: '1',
  interval: '24',
  observation: String(DEFAULT_OBSERVATION_MINUTES),
  instructions: '',
}

/**
 * "Aplicaciones en clínica": what nursing should apply here. They are drafts until the
 * consultation is signed, when they become orders on the nursing worklist.
 */
export function ConsultationApplications({
  consultationId,
  consultation,
}: {
  consultationId: string
  consultation: Consultation
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState(EMPTY)
  const set = (patch: Partial<typeof EMPTY>) => setForm((f) => ({ ...f, ...patch }))
  const multi = Number(form.doses) > 1

  const add = useMutation({
    mutationFn: () =>
      consultationsApi.addApplication(consultationId, {
        drug: form.drug.trim(),
        dose: form.dose.trim(),
        route: form.route,
        doses_total: Number(form.doses) || 1,
        interval_hours: multi ? Number(form.interval) || null : null,
        observation_minutes: Number(form.observation) || 0,
        instructions: form.instructions.trim() || null,
      }),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setForm(EMPTY)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (index: number) => consultationsApi.removeApplication(consultationId, index),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const drafts = consultation.draft_applications

  return (
    <section>
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-tx">{t('apl.consult_title')}</h3>
        <span className="text-xs text-tx-3">
          {drafts.length} {t('apl.consult_unit')}
        </span>
      </div>
      <p className="mb-3 text-xs text-tx-3">{t('apl.consult_hint')}</p>
      <div className="space-y-2">
        {drafts.map((a, i) => (
          <div
            key={i}
            className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2"
          >
            <Syringe className="h-4 w-4 shrink-0 text-accent" />
            <div className="flex-1">
              <p className="text-sm font-medium text-tx">
                {a.drug} {a.dose} · {t(`apl.route_short.${a.route}`)}
              </p>
              <p className="text-xs text-tx-3">
                {planLabel(t, a)} ·{' '}
                {a.observation_minutes > 0
                  ? t('apl.obs_minutes').replace('{n}', String(a.observation_minutes))
                  : t('apl.no_observation')}
                {a.instructions ? ` · ${a.instructions}` : ''}
              </p>
            </div>
            <button
              type="button"
              onClick={() => remove.mutate(i)}
              className="text-tx-4 hover:text-danger"
              aria-label={t('apl.remove')}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-3 rounded-xl border border-line bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1.4fr_1fr_1fr]">
          <Input
            label={t('apl.drug')}
            value={form.drug}
            placeholder={t('apl.drug_ph')}
            onChange={(e) => set({ drug: e.target.value })}
          />
          <Input
            label={t('apl.dose')}
            value={form.dose}
            placeholder={t('apl.dose_ph')}
            onChange={(e) => set({ dose: e.target.value })}
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
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[100px_100px_120px_1fr]">
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
          <Input
            label={t('apl.instructions')}
            value={form.instructions}
            onChange={(e) => set({ instructions: e.target.value })}
          />
        </div>
        <Button
          size="sm"
          disabled={!form.drug.trim() || !form.dose.trim()}
          loading={add.isPending}
          onClick={() => add.mutate()}
        >
          <Plus className="h-4 w-4" />
          {t('apl.add')}
        </Button>
      </div>
    </section>
  )
}

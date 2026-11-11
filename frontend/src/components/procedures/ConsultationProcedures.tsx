import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardList, Plus, Trash2 } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { consultationsApi } from '@/api/consultations'
import { proceduresApi } from '@/api/procedures'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input, Select } from '@/components/ui/Input'
import { toast } from '@/components/ui/Toast'
import { fmtFee, useCanPrice } from '@/lib/fees'
import { useT } from '@/lib/i18n'
import type { Consultation } from '@/types'

/**
 * "Procedimientos": what to do here (suture, biopsy…). Drafts until the consultation is
 * signed, when they become pending procedures on the worklist.
 */
export function ConsultationProcedures({
  consultationId,
  consultation,
}: {
  consultationId: string
  consultation: Consultation
}) {
  const t = useT()
  const qc = useQueryClient()
  const [typeId, setTypeId] = useState('')
  const [indication, setIndication] = useState('')
  const [included, setIncluded] = useState(false)
  // Charging nothing for it is a fee decision: only who may set this doctor's fees.
  const canPrice = useCanPrice()(consultation.doctor_id)
  const { data: catalog } = useQuery({
    queryKey: ['procedure-catalog'],
    queryFn: proceduresApi.catalog,
  })

  const add = useMutation({
    mutationFn: () =>
      consultationsApi.addProcedure(consultationId, {
        type_id: typeId,
        indication: indication.trim(),
        included,
      }),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setTypeId('')
      setIndication('')
      setIncluded(false)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (index: number) => consultationsApi.removeProcedure(consultationId, index),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const drafts = consultation.draft_procedures
  const types = (catalog ?? []).filter((k) => k.active)

  return (
    <section>
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-tx">{t('prc.consult_title')}</h3>
        <span className="text-xs text-tx-3">
          {drafts.length} {t('prc.consult_unit')}
        </span>
      </div>
      <p className="mb-3 text-xs text-tx-3">{t('prc.consult_hint')}</p>
      <div className="space-y-2">
        {drafts.map((d, i) => (
          <div
            key={i}
            className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2"
          >
            <ClipboardList className="h-4 w-4 shrink-0 text-accent" />
            <div className="flex-1">
              <p className="text-sm font-medium text-tx">{d.type_name}</p>
              <p className="text-xs text-tx-3">
                {d.indication} · {t(`prc.performer.${d.performer}`)}
                {d.requires_consent ? ` · ${t('prc.consent_badge')}` : ''}
                {d.follow_up_days
                  ? ` · ${t('prc.follow_up_in').replace('{n}', String(d.follow_up_days))}`
                  : ''}
              </p>
            </div>
            {d.included ? (
              <Badge tone="info">{t('fee.included')}</Badge>
            ) : (
              d.price && <span className="font-mono text-xs text-tx-2">{fmtFee(d.price)}</span>
            )}
            <button
              type="button"
              onClick={() => remove.mutate(i)}
              className="text-tx-4 hover:text-danger"
              aria-label={t('prc.remove')}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-3 rounded-xl border border-line bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1.4fr]">
          <Select label={t('prc.type')} value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            <option value="">{t('prc.type_ph')}</option>
            {types.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </Select>
          <Input
            label={t('prc.indication')}
            placeholder={t('prc.indication_ph')}
            value={indication}
            onChange={(e) => setIndication(e.target.value)}
          />
        </div>
        {canPrice && (
          <label className="flex items-start gap-2 text-sm text-tx-2">
            <Checkbox
              className="mt-0.5"
              checked={included}
              onChange={(e) => setIncluded(e.target.checked)}
            />
            <span>
              {t('fee.included')}
              <span className="block text-xs text-tx-3">{t('fee.included_hint')}</span>
            </span>
          </label>
        )}
        <Button
          size="sm"
          disabled={!typeId || !indication.trim()}
          loading={add.isPending}
          onClick={() => add.mutate()}
        >
          <Plus className="h-4 w-4" />
          {t('prc.consult_add')}
        </Button>
      </div>
    </section>
  )
}

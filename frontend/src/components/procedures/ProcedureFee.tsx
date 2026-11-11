import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BadgeDollarSign } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { type ProcedureDetail, proceduresApi } from '@/api/procedures'
import { AdjustFeeModal } from '@/components/fees/AdjustFeeModal'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { toast } from '@/components/ui/Toast'
import { fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'

/** What the procedure is charged: the catalog price when it was ordered, an adjusted amount,
 * or included in the consultation it was indicated in (only those may be). */
export function ProcedureFee({ data }: { data: ProcedureDetail }) {
  const t = useT()
  const qc = useQueryClient()
  const [adjusting, setAdjusting] = useState(false)
  const p = data.procedure
  const editable = data.fee_editable && p.status !== 'cancelled'

  const setFee = useMutation({
    mutationFn: (v: { included: boolean; amount: string | null; note: string | null }) =>
      proceduresApi.setFee(p.id, v),
    onSuccess: (detail) => {
      qc.setQueryData(['procedure', p.id], detail)
      qc.invalidateQueries({ queryKey: ['procedures'] })
      toast(t('fee.adjusted_ok'))
      setAdjusting(false)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (p.status === 'cancelled' || (!editable && p.fee === null)) return null
  const adjusted =
    !p.fee_included && p.listed_fee !== null && Number(p.listed_fee) !== Number(p.fee)

  return (
    <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
      <div className="flex items-start gap-3">
        <BadgeDollarSign className="mt-0.5 h-4 w-4 text-tx-3" />
        <div>
          <p className="text-sm font-semibold text-tx">{t('fee.col_fee')}</p>
          {p.fee_included ? (
            <p className="mt-0.5 text-sm text-tx-2">
              <Badge tone="info">{t('fee.included')}</Badge>
              {p.listed_fee && (
                <span className="ml-2 text-xs text-tx-3">
                  {t('fee.listed').replace('{price}', fmtFee(p.listed_fee)!)}
                </span>
              )}
            </p>
          ) : (
            <p className="mt-0.5 font-mono text-sm text-tx">
              {adjusted && (
                <span className="mr-2 text-xs text-tx-4 line-through">{fmtFee(p.listed_fee)}</span>
              )}
              {fmtFee(p.fee) ?? <span className="font-sans text-tx-3">{t('fee.no_price')}</span>}
            </p>
          )}
          {p.fee_note && <p className="mt-0.5 text-xs text-tx-3">{p.fee_note}</p>}
        </div>
      </div>
      {editable && (
        <div className="flex flex-wrap gap-2">
          {p.consultation_id &&
            (p.fee_included ? (
              <Button
                variant="outline"
                size="sm"
                loading={setFee.isPending}
                onClick={() =>
                  p.listed_fee !== null
                    ? setFee.mutate({ included: false, amount: p.listed_fee, note: null })
                    : setAdjusting(true)
                }
              >
                {t('fee.charge_separately')}
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                loading={setFee.isPending}
                onClick={() => setFee.mutate({ included: true, amount: null, note: null })}
              >
                {t('fee.include')}
              </Button>
            ))}
          <Button variant="outline" size="sm" onClick={() => setAdjusting(true)}>
            {t('fee.adjust')}
          </Button>
        </div>
      )}
      <AdjustFeeModal
        open={adjusting}
        subtitle={`${p.type_name} · ${data.patient.name}`}
        listed={p.listed_fee}
        charged={p.fee_included ? null : p.fee}
        note={p.fee_note}
        loading={setFee.isPending}
        onClose={() => setAdjusting(false)}
        onSave={(amount, note) => setFee.mutate({ included: false, amount, note })}
      />
    </Card>
  )
}

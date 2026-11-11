import { fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'
import type { Appointment } from '@/types'

/** An appointment's charge in a table cell: what is charged, the listed fee struck through
 * when they differ (the note in the tooltip), or why there is no amount. */
export function FeeCell({ appointment: a }: { appointment: Appointment }) {
  const t = useT()
  if (a.status === 'cancelled') return <span className="text-tx-4">—</span>
  if (a.fee === null) {
    return (
      <span className="text-xs text-tx-4">
        {a.type === 'procedure' ? t('fee.by_procedure') : t('fee.none')}
      </span>
    )
  }
  const adjusted = a.listed_fee !== null && Number(a.listed_fee) !== Number(a.fee)
  return (
    <span className="font-mono text-sm text-tx" title={a.fee_note ?? undefined}>
      {adjusted && (
        <span className="mr-1.5 text-xs text-tx-4 line-through">{fmtFee(a.listed_fee)}</span>
      )}
      {fmtFee(a.fee)}
    </span>
  )
}

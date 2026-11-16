import { useT } from '@/lib/i18n'

/** The visit's total before saving: private doses at the clinic's prices, MINSAL ones free. */
export function VisitTotal({ cents, minsal }: { cents: number; minsal: number }) {
  const t = useT()
  return (
    <p aria-live="polite" className="rounded-lg bg-surface-2 px-3 py-2 text-sm font-medium text-tx">
      {t('vax.total').replace('{total}', `$${(cents / 100).toFixed(2)}`)}
      {minsal > 0 && (
        <span className="font-normal text-tx-3">
          {' · '}
          {minsal === 1
            ? t('vax.total_minsal_one')
            : t('vax.total_minsal').replace('{n}', String(minsal))}
        </span>
      )}
    </p>
  )
}

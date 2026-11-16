import { useId } from 'react'
import { Link } from 'react-router-dom'
import type { VaccineSupply } from '@/api/vaccinations'
import { cn } from '@/lib/cn'
import { fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

const OPTIONS: VaccineSupply[] = ['clinic', 'minsal']

/**
 * Who supplied the dose: the clinic (private, charged at its price) or the ministry (MINSAL,
 * free). The choice is explicit for vaccines in the national scheme, where either can apply.
 */
export function SupplyField({
  value,
  price,
  onChange,
}: {
  value: VaccineSupply | ''
  /** The clinic's price for the vaccine; null when it has none. */
  price: string | null
  onChange: (supply: VaccineSupply) => void
}) {
  const t = useT()
  const canPrice = useAuthStore((s) => s.can('fees.manage_all'))
  const group = useId()
  const warnId = useId()
  const missing = value === 'clinic' && price === null

  const label = (s: VaccineSupply) =>
    s === 'minsal'
      ? t('vax.supply.minsal_free')
      : price === null
        ? t('vax.supply.clinic')
        : t('vax.supply.clinic_price').replace('{price}', fmtFee(price)!)

  return (
    <fieldset aria-describedby={missing ? warnId : undefined}>
      <legend className="mb-1.5 text-[13px] font-medium text-tx-2">{t('vax.supply')}</legend>
      <div className="flex flex-wrap gap-2">
        {OPTIONS.map((s) => (
          <label
            key={s}
            className={cn(
              'flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm',
              'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent',
              value === s ? 'border-accent bg-[var(--accent-10)] text-tx' : 'border-line text-tx-2',
            )}
          >
            <input
              type="radio"
              name={group}
              value={s}
              checked={value === s}
              onChange={() => onChange(s)}
              className="accent-[var(--accent)]"
            />
            {label(s)}
          </label>
        ))}
      </div>
      {missing && (
        <p id={warnId} role="alert" className="mt-1.5 text-xs text-danger">
          {t('vax.supply.no_price')}{' '}
          {canPrice && (
            <Link to="/fees" className="underline">
              {t('vax.supply.set_price')}
            </Link>
          )}
        </p>
      )}
    </fieldset>
  )
}

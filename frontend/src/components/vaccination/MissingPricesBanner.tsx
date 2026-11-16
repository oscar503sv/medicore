import { Link } from 'react-router-dom'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useVaccinePrices } from './useVaccinePrices'

/** Tells whoever sets the prices that none are loaded yet: without them a private dose
 * cannot be recorded. Nobody else is shown it (they cannot act on it). */
export function MissingPricesBanner() {
  const t = useT()
  const canPrice = useAuthStore((s) => s.can('fees.manage_all'))
  const { isEmpty } = useVaccinePrices(canPrice)
  if (!canPrice || !isEmpty) return null
  return (
    <p role="status" className="rounded-lg bg-[var(--warn-10)] px-4 py-3 text-sm text-tx">
      {t('vax.prices_missing')}{' '}
      <Link to="/fees" className="font-medium text-accent underline">
        {t('vax.supply.set_price')}
      </Link>
    </p>
  )
}

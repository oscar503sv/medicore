import type { VaccinationRecord } from '@/api/vaccinations'
import { Badge } from '@/components/ui/Badge'
import { fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'

/** Where a dose given at the clinic came from, with its price when it was charged. Doses
 * recorded before the field existed show nothing. */
export function SupplyBadge({
  record,
}: {
  record: Pick<VaccinationRecord, 'supply' | 'listed_fee'>
}) {
  const t = useT()
  if (record.supply === 'minsal') return <Badge tone="info">{t('vax.supply_short.minsal')}</Badge>
  if (record.supply !== 'clinic') return null
  return (
    <Badge tone="neutral">
      {record.listed_fee === null
        ? t('vax.supply_short.clinic')
        : t('vax.supply.badge_clinic').replace('{price}', fmtFee(record.listed_fee)!)}
    </Badge>
  )
}

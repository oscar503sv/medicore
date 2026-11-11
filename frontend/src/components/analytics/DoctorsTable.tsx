import type { AnalyticsOverview } from '@/api/analytics'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtIncome, fmtRate } from '@/lib/analytics'
import { useT } from '@/lib/i18n'

/** Clinic scope: each doctor's figures for the period, busiest first. */
export function DoctorsTable({
  rows,
  money,
}: {
  rows: NonNullable<AnalyticsOverview['doctors']>
  money: boolean
}) {
  const t = useT()
  if (rows.length === 0)
    return <p className="px-5 py-8 text-center text-sm text-tx-3">{t('an.no_data')}</p>
  return (
    <Table>
      <thead>
        <Tr>
          <Th>{t('an.col_doctor')}</Th>
          <Th className="text-right">{t('an.attended')}</Th>
          <Th className="text-right">{t('an.patients')}</Th>
          <Th className="text-right">{t('an.new_patients')}</Th>
          <Th className="text-right">{t('an.no_show_rate')}</Th>
          <Th className="text-right">{t('an.cancelled')}</Th>
          {money && <Th className="text-right">{t('an.income')}</Th>}
        </Tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <Tr key={r.doctor_id}>
            <Td className="font-medium text-tx">{r.name}</Td>
            <Td className="text-right font-mono">{r.totals.attended}</Td>
            <Td className="text-right font-mono">{r.totals.patients}</Td>
            <Td className="text-right font-mono">{r.totals.new_patients}</Td>
            <Td className="text-right font-mono">{fmtRate(r.totals.no_show_rate)}</Td>
            <Td className="text-right font-mono">{r.totals.cancelled}</Td>
            {money && <Td className="text-right font-mono">{fmtIncome(r.totals.income)}</Td>}
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

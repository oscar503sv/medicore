import { Card, CardHeader } from '@/components/ui/Card'
import { Table, Td, Th } from '@/components/ui/Table'
import { fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { VITAL_COLS, hasAnyVital, type VitalCol } from './vitalsData'
import type { MedicalRecord, Vitals } from '@/types'

/** A single vital reading as a bordered stat card (icon + label, value + unit). */
export function VitalStat({ col, value }: { col: VitalCol; value: NonNullable<Vitals[keyof Vitals]> }) {
  const Icon = col.icon
  return (
    <div className="rounded-lg border border-line bg-surface p-2.5 text-center">
      <p className="flex items-center justify-center gap-1 text-tx-3">
        <Icon className="h-3 w-3" />
        <span className="eyebrow">{col.label}</span>
      </p>
      <p className="mt-0.5 font-serif text-lg text-tx">
        {col.fmt(value)}
        <span className="ml-1 text-sm text-tx-3">{col.unit}</span>
      </p>
    </div>
  )
}

/** Latest reading as headline cards, plus a full history table — newest first. */
export function VitalsHistory({ records }: { records: MedicalRecord[] }) {
  const t = useT()
  const rows = records
    .filter((r) => hasAnyVital(r.vitals))
    .sort((a, b) => b.encounter_at.localeCompare(a.encounter_at))

  if (rows.length === 0)
    return <Card className="p-8 text-center text-sm text-tx-3">{t('patient.vitals_empty')}</Card>

  const latest = rows[0]
  const latestCols = VITAL_COLS.filter((c) => latest.vitals[c.key] != null)

  return (
    <div className="space-y-6">
      {/* Latest reading */}
      <div>
        <p className="eyebrow mb-2">
          {t('patient.vitals_latest')} · {fmtDateTz(latest.encounter_at)}
        </p>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {latestCols.map((c) => (
            <VitalStat key={c.key} col={c} value={latest.vitals[c.key]!} />
          ))}
        </div>
      </div>

      {/* History table */}
      <Card>
        <CardHeader title={t('patient.vitals_history')} />
        <Table>
          <thead>
            <tr>
              <Th>{t('patient.vitals_date')}</Th>
              {VITAL_COLS.map((c) => (
                <Th key={c.key}>{c.label}</Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <Td className="whitespace-nowrap font-medium text-tx">{fmtDateTz(r.encounter_at)}</Td>
                {VITAL_COLS.map((c) => (
                  <Td key={c.key} className="whitespace-nowrap">
                    {r.vitals[c.key] != null ? (
                      <>
                        {c.fmt(r.vitals[c.key]!)}
                        <span className="ml-1 text-xs text-tx-4">{c.unit}</span>
                      </>
                    ) : (
                      '—'
                    )}
                  </Td>
                ))}
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  )
}

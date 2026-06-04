import { Card } from '@/components/ui/Card'
import { fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { MedicalRecord } from '@/types'

/** Shape of a prescription snapshot embedded in a signed record. */
interface Rx {
  drug: string
  dose: string
  schedule: string
  duration_days: number | null
}

/**
 * Medication history as a vertical timeline: one node per signed record that carried
 * prescriptions, newest first, with each drug rendered as a card under its node.
 */
export function MedicationTimeline({ records }: { records: MedicalRecord[] }) {
  const t = useT()
  const nodes = records
    .filter((r) => (r.prescriptions?.length ?? 0) > 0)
    .sort((a, b) => b.encounter_at.localeCompare(a.encounter_at))

  if (nodes.length === 0)
    return <Card className="p-8 text-center text-sm text-tx-3">{t('patient.meds_empty')}</Card>

  return (
    <div className="relative pl-7">
      {/* Spine */}
      <div className="absolute bottom-2 left-[7px] top-2 w-px bg-line" />
      <div className="space-y-7">
        {nodes.map((r) => (
          <div key={r.id} className="relative">
            <span className="absolute -left-7 top-1 h-3.5 w-3.5 rounded-full border-2 border-accent bg-surface" />
            <p className="text-[13px]">
              <span className="font-medium text-tx">{fmtDateTz(r.encounter_at)}</span>
              <span className="mx-1.5 text-tx-4">·</span>
              <span className="font-mono text-tx-3">{r.code}</span>
            </p>
            <div className="mt-2 space-y-1.5">
              {(r.prescriptions as Rx[]).map((rx, i) => (
                <div key={i} className="rounded-lg border border-line bg-surface px-3 py-2">
                  <p className="text-sm font-medium text-tx">{rx.drug}</p>
                  <p className="text-xs text-tx-3">
                    {rx.dose} · {rx.schedule}
                    {rx.duration_days ? ` · ${rx.duration_days} ${t('patient.meds_days')}` : ''}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

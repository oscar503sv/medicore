import { useQuery } from '@tanstack/react-query'
import { prescriptionsApi } from '@/api/prescriptions'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Prescription } from '@/types'

/** Prescriptions issued together (the same signed visit, or the same day when manual). */
function groupPrescriptions(items: Prescription[]): Prescription[][] {
  const groups = new Map<string, Prescription[]>()
  for (const rx of items) {
    const key = rx.record_id ?? rx.start_date
    groups.set(key, [...(groups.get(key) ?? []), rx])
  }
  return [...groups.values()].sort((a, b) => b[0].start_date.localeCompare(a[0].start_date))
}

/**
 * Medication history as a vertical timeline: one node per visit (or day) that carried
 * prescriptions, newest first, with each drug rendered as a card under its node. It reads the
 * same prescriptions as the list above it, so it adds no request.
 */
export function MedicationTimeline({ patientId }: { patientId: string }) {
  const t = useT()
  const { data, isLoading } = useQuery({
    queryKey: ['prescriptions', patientId],
    queryFn: () => prescriptionsApi.list(patientId),
  })

  if (isLoading) return <PageLoader />
  const nodes = groupPrescriptions(data ?? [])

  if (nodes.length === 0)
    return <Card className="p-8 text-center text-sm text-tx-3">{t('patient.meds_empty')}</Card>

  return (
    <div className="relative pl-7">
      {/* Spine */}
      <div className="absolute bottom-2 left-[7px] top-2 w-px bg-line" />
      <div className="space-y-7">
        {nodes.map((group) => (
          <div key={group[0].record_id ?? group[0].start_date} className="relative">
            <span className="absolute -left-7 top-1 h-3.5 w-3.5 rounded-full border-2 border-accent bg-surface" />
            <p className="text-[13px]">
              <span className="font-medium text-tx">{fmtDate(group[0].start_date)}</span>
              {group[0].prescriber_name && (
                <>
                  <span className="mx-1.5 text-tx-4">·</span>
                  <span className="text-tx-3">{group[0].prescriber_name}</span>
                </>
              )}
            </p>
            <div className="mt-2 space-y-1.5">
              {group.map((rx) => (
                <div key={rx.id} className="rounded-lg border border-line bg-surface px-3 py-2">
                  <div className="flex items-center gap-2">
                    <p
                      className={`text-sm font-medium text-tx ${rx.status === 'cancelled' ? 'line-through' : ''}`}
                    >
                      {rx.drug}
                    </p>
                    {rx.status === 'cancelled' && (
                      <span className="text-xs text-tx-3">{t('rx.status_cancelled')}</span>
                    )}
                  </div>
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

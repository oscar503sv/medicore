import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Printer, X } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { openPrint } from '@/api/printing'
import { prescriptionsApi } from '@/api/prescriptions'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { CancelPrescriptionModal } from '@/components/patients/CancelPrescriptionModal'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useFill } from '@/lib/printing'
import { useAuthStore } from '@/stores/auth'
import type { Prescription } from '@/types'

/** Derived display state: an active prescription past its end date shows as expired. */
function displayStatus(rx: Prescription): 'active' | 'expired' | 'completed' | 'cancelled' {
  if (rx.status === 'active' && rx.end_date && rx.end_date < clinicToday()) return 'expired'
  return rx.status
}

const STATUS_TONE = {
  active: 'ok',
  expired: 'warn',
  completed: 'neutral',
  cancelled: 'danger',
} as const

export function PrescriptionList({ patientId }: { patientId: string }) {
  const t = useT()
  const f = useFill()
  const qc = useQueryClient()
  const userId = useAuthStore((s) => s.session?.user_id)
  const [cancelling, setCancelling] = useState<Prescription | null>(null)
  const canManage = useAuthStore((s) => s.can('prescriptions.manage'))
  const canPrint = useAuthStore((s) => s.can('records.view'))

  const { data: items, isLoading } = useQuery({
    queryKey: ['prescriptions', patientId],
    queryFn: () => prescriptionsApi.list(patientId),
  })

  const complete = useMutation({
    mutationFn: (id: string) => prescriptionsApi.complete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prescriptions', patientId] })
      // The summary's active-prescriptions counter comes from the patient detail.
      qc.invalidateQueries({ queryKey: ['patient', patientId] })
      toast(t('rx.completed_ok'))
    },
    onError: (err) => {
      toast(errorMessage(err), 'danger')
      qc.invalidateQueries({ queryKey: ['prescriptions', patientId] })
    },
  })

  if (isLoading) return <PageLoader />
  if (!items || items.length === 0)
    return <Card className="p-8 text-center text-sm text-tx-3">{t('rx.empty')}</Card>

  return (
    <>
      <Card className="divide-y divide-line">
        {items.map((rx) => {
          const status = displayStatus(rx)
          // Only the prescriber closes a prescription; the backend enforces it too.
          const actionable = canManage && rx.status === 'active' && rx.prescriber_id === userId
          return (
            <div key={rx.id} className="flex items-center gap-4 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-tx">{rx.drug}</p>
                  <Badge tone={STATUS_TONE[status]}>{t(`rx.status_${status}`)}</Badge>
                </div>
                <p className="mt-0.5 text-xs text-tx-3">
                  {rx.dose} · {rx.schedule}
                  {rx.prescriber_name ? ` · ${rx.prescriber_name}` : ''}
                </p>
                <p className="mt-0.5 text-xs text-tx-4">
                  {fmtDate(rx.start_date)}
                  {rx.end_date ? ` → ${fmtDate(rx.end_date)}` : ` · ${t('rx.indefinite')}`}
                </p>
                {rx.status === 'cancelled' && (
                  <p className="mt-0.5 text-xs text-tx-3">
                    {rx.closed_at && f('rx.cancelled_on', { date: fmtDate(rx.closed_at) })}
                    {rx.cancel_reason &&
                      `${rx.closed_at ? ' · ' : ''}${f('rx.cancel_reason_shown', { reason: rx.cancel_reason })}`}
                  </p>
                )}
              </div>
              {canPrint && rx.record_id && rx.status !== 'cancelled' && (
                <Button
                  size="sm"
                  variant="ghost"
                  title={t('pr.btn.prescription')}
                  onClick={() => openPrint(`prescription/${rx.record_id}`)}
                >
                  <Printer className="h-3.5 w-3.5" />
                </Button>
              )}
              {actionable && (
                <div className="flex shrink-0 gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={complete.isPending}
                    title={t('rx.complete_hint')}
                    onClick={() => complete.mutate(rx.id)}
                  >
                    <Check className="h-3.5 w-3.5" />
                    {t('rx.complete')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setCancelling(rx)}>
                    <X className="h-3.5 w-3.5" />
                    {t('rx.cancel')}
                  </Button>
                </div>
              )}
            </div>
          )
        })}
      </Card>
      <CancelPrescriptionModal prescription={cancelling} onClose={() => setCancelling(null)} />
    </>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { prescriptionsApi } from '@/api/prescriptions'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
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
  const qc = useQueryClient()
  const canManage = useAuthStore((s) => s.can('prescriptions.manage'))

  const { data: items, isLoading } = useQuery({
    queryKey: ['prescriptions', patientId],
    queryFn: () => prescriptionsApi.list(patientId),
  })

  const transition = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'complete' | 'cancel' }) =>
      action === 'complete' ? prescriptionsApi.complete(id) : prescriptionsApi.cancel(id),
    onSuccess: (_, { action }) => {
      qc.invalidateQueries({ queryKey: ['prescriptions', patientId] })
      // The summary's active-prescriptions counter comes from the patient detail.
      qc.invalidateQueries({ queryKey: ['patient', patientId] })
      toast(t(action === 'complete' ? 'rx.completed_ok' : 'rx.cancelled_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading) return <PageLoader />
  if (!items || items.length === 0)
    return <Card className="p-8 text-center text-sm text-tx-3">{t('rx.empty')}</Card>

  return (
    <Card className="divide-y divide-line">
      {items.map((rx) => {
        const status = displayStatus(rx)
        const actionable = canManage && rx.status === 'active'
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
            </div>
            {actionable && (
              <div className="flex shrink-0 gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={transition.isPending}
                  onClick={() => transition.mutate({ id: rx.id, action: 'complete' })}
                >
                  <Check className="h-3.5 w-3.5" />
                  {t('rx.complete')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={transition.isPending}
                  onClick={() => transition.mutate({ id: rx.id, action: 'cancel' })}
                >
                  <X className="h-3.5 w-3.5" />
                  {t('rx.cancel')}
                </Button>
              </div>
            )}
          </div>
        )
      })}
    </Card>
  )
}

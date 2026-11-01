import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Ban, Pill, Syringe, XCircle } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { applicationsApi, type ApplicationOrder, type ApplicationRecord } from '@/api/applications'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Menu } from '@/components/ui/Menu'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { ORDER_TONE, originLabel, planLabel } from '@/lib/applications'
import { cn } from '@/lib/cn'
import { fmtDate, fmtDateTime, fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { ApplyModal, type ApplyTarget } from './ApplyModal'
import { ObservationActions, ObservationTimer } from './ObservationActions'
import { ReasonModal } from './ReasonModal'

const OPEN = new Set(['pending', 'in_progress'])

/** Patient tab: every application order (internal or external) with its dose history. */
export function PatientApplications({
  patientId,
  patientName,
  active,
}: {
  patientId: string
  patientName: string
  /** Archived patients can't get new doses. */
  active: boolean
}) {
  const t = useT()
  const qc = useQueryClient()
  const canAdminister = useAuthStore((s) => s.can('applications.administer'))
  const [applying, setApplying] = useState<ApplyTarget | null>(null)
  const [cancelling, setCancelling] = useState<ApplicationOrder | null>(null)
  const [voiding, setVoiding] = useState<ApplicationRecord | null>(null)

  const { data: orders } = useQuery({
    queryKey: ['applications-patient', patientId],
    queryFn: () => applicationsApi.patient(patientId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['applications-patient', patientId] })
    qc.invalidateQueries({ queryKey: ['applications-worklist'] })
  }
  const cancel = useMutation({
    mutationFn: (reason: string) => applicationsApi.cancel(cancelling!.id, reason),
    onSuccess: () => {
      refresh()
      toast(t('apl.cancel_ok'))
      setCancelling(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const voidRecord = useMutation({
    mutationFn: (reason: string) => applicationsApi.void(voiding!.id, reason),
    onSuccess: () => {
      refresh()
      toast(t('apl.void_ok'))
      setVoiding(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (!orders) return <PageLoader />
  if (orders.length === 0) {
    return (
      <Card>
        <EmptyState icon={Syringe} title={t('apl.empty_patient')} />
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {orders.map((order) => {
        const open = OPEN.has(order.status)
        const canAct = canAdminister && open
        return (
          <Card key={order.id} className="overflow-hidden">
            {/* Order header */}
            <div className="flex flex-wrap items-start gap-3 border-b border-line bg-surface-2/40 px-5 py-3.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-10)] text-accent">
                <Pill className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-tx">
                    {order.drug} {order.dose}
                  </p>
                  <span className="text-xs text-tx-3">{t(`apl.route.${order.route}`)}</span>
                  <Badge tone={ORDER_TONE[order.status]}>{t(`apl.status.${order.status}`)}</Badge>
                  <Badge tone={order.source === 'external' ? 'accent' : 'neutral'}>
                    {t(`apl.source.${order.source}`)}
                  </Badge>
                </div>
                <p className="mt-0.5 text-xs text-tx-3">
                  {planLabel(t, order)} ·{' '}
                  {order.observation_minutes > 0
                    ? t('apl.obs_minutes').replace('{n}', String(order.observation_minutes))
                    : t('apl.no_observation')}{' '}
                  · {originLabel(t, order)} · {fmtDate(order.starts_at)}
                </p>
                {order.instructions && (
                  <p className="mt-1 text-xs text-tx-2">{order.instructions}</p>
                )}
                {open && order.allergy_conflicts.length > 0 && (
                  <p className="mt-1 flex items-center gap-1 text-xs font-medium text-danger">
                    <AlertTriangle className="h-3 w-3" />
                    {t('apl.allergy_flag').replace('{list}', order.allergy_conflicts.join(', '))}
                  </p>
                )}
                {open && order.next_due_at && (
                  <p className="mt-1 text-xs text-tx-2">
                    {t('apl.dose_of')
                      .replace('{n}', String(order.next_dose ?? 1))
                      .replace('{total}', String(order.doses_total))}{' '}
                    · {t('apl.next_due').replace('{when}', fmtDateTime(order.next_due_at))}
                  </p>
                )}
                {order.status === 'cancelled' && (
                  <p className="mt-1 text-xs text-tx-3">
                    {t('apl.cancelled_by')
                      .replace('{name}', order.cancelled_by_name ?? '—')
                      .replace('{reason}', order.cancel_reason ?? '')}
                  </p>
                )}
              </div>
              {canAct && active && (
                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="accent"
                    onClick={() => setApplying({ order, patientName })}
                  >
                    <Syringe className="h-3.5 w-3.5" />
                    {t('apl.apply')}
                  </Button>
                  <Menu
                    label={t('apl.cancel_order')}
                    items={[
                      {
                        label: t('apl.cancel_order'),
                        icon: XCircle,
                        tone: 'danger',
                        onSelect: () => setCancelling(order),
                      },
                    ]}
                  />
                </div>
              )}
            </div>

            {/* Dose history */}
            {order.records.length > 0 && (
              <div className="divide-y divide-line-soft">
                {order.records.map((r) => (
                  <RecordRow
                    key={r.id}
                    record={r}
                    order={order}
                    canAdminister={canAdminister}
                    onVoid={() => setVoiding(r)}
                  />
                ))}
              </div>
            )}
          </Card>
        )
      })}

      <ApplyModal target={applying} onClose={() => setApplying(null)} />
      <ReasonModal
        open={cancelling !== null}
        title={t('apl.cancel_title')}
        description={t('apl.cancel_desc')}
        confirmLabel={t('apl.cancel_order')}
        loading={cancel.isPending}
        onConfirm={(reason) => cancel.mutate(reason)}
        onClose={() => setCancelling(null)}
      />
      <ReasonModal
        open={voiding !== null}
        title={t('apl.void_title')}
        description={t('apl.void_desc')}
        confirmLabel={t('apl.void')}
        loading={voidRecord.isPending}
        onConfirm={(reason) => voidRecord.mutate(reason)}
        onClose={() => setVoiding(null)}
      />
    </div>
  )
}

function RecordRow({
  record: r,
  order,
  canAdminister,
  onVoid,
}: {
  record: ApplicationRecord
  order: ApplicationOrder
  canAdminister: boolean
  onVoid: () => void
}) {
  const t = useT()
  const voided = r.voided_at !== null
  const observing = !voided && r.observe_until !== null && r.observation_closed_at === null
  const details = [
    r.lot && `${t('apl.lot')} ${r.lot}${r.lot_expiry ? ` (${fmtDate(r.lot_expiry)})` : ''}`,
    r.site && t(`apl.site.${r.site}`),
    r.blood_pressure && `${t('apl.bp')} ${r.blood_pressure}`,
    r.temperature !== null && `${r.temperature} °C`,
  ].filter(Boolean)

  return (
    <div className="flex items-start gap-3 px-5 py-3">
      <span className="mt-0.5 w-14 shrink-0 font-mono text-xs text-tx-3">
        #{r.dose_number}/{order.doses_total}
      </span>
      <div className={cn('min-w-0 flex-1', voided && 'opacity-60')}>
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn('text-sm text-tx', voided && 'line-through')}>
            {fmtDateTimeTz(r.recorded_at)}
          </span>
          <Badge tone={r.outcome === 'applied' ? 'ok' : 'warn'}>
            {t(`apl.outcome.${r.outcome}`)}
          </Badge>
          {r.reaction && <Badge tone="danger">{t('apl.reaction')}</Badge>}
          {voided && (
            <Badge tone="neutral">
              <Ban className="mr-1 h-3 w-3" />
              {t('apl.void')}
            </Badge>
          )}
          <span className="text-xs text-tx-3">
            {t('apl.by').replace('{name}', r.recorded_by_name ?? '—')}
          </span>
        </div>
        {details.length > 0 && (
          <p className={cn('mt-0.5 text-xs text-tx-3', voided && 'line-through')}>
            {details.join(' · ')}
          </p>
        )}
        {r.allergy_override && (
          <p className="mt-0.5 text-xs text-warn">
            {t('apl.override_noted').replace('{reason}', r.allergy_override)}
          </p>
        )}
        {r.reaction && r.reaction_notes && (
          <p className="mt-0.5 text-xs text-danger">
            {t('apl.reaction_noted').replace('{notes}', r.reaction_notes)}
          </p>
        )}
        {r.notes && <p className="mt-0.5 text-xs text-tx-2">{r.notes}</p>}
        {voided && (
          <p className="mt-0.5 text-xs text-tx-3">
            {t('apl.voided_by')
              .replace('{name}', r.voided_by_name ?? '—')
              .replace('{reason}', r.void_reason ?? '')}
          </p>
        )}
        {observing && (
          <div className="mt-1.5">
            <ObservationTimer record={r} />
          </div>
        )}
      </div>
      {canAdminister && observing && <ObservationActions record={r} order={order} />}
      {canAdminister && !voided && !observing && (
        <Menu
          label={t('apl.void')}
          items={[{ label: t('apl.void'), icon: Ban, tone: 'danger', onSelect: onVoid }]}
        />
      )}
    </div>
  )
}

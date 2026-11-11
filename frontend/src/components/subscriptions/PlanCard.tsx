import { useQuery } from '@tanstack/react-query'
import { organizationApi } from '@/api/organization'
import { Card, CardHeader } from '@/components/ui/Card'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { expiryLabel, fmtUsd, limitLabel } from '@/lib/subscriptions'
import { PaymentsTable } from './PaymentsCard'
import { SubscriptionBadge } from './SubscriptionBadge'

/** Settings → Organization: the clinic's plan, read-only (changes go through Medicore). */
export function PlanCard() {
  const t = useT()
  const { data: sub } = useQuery({
    queryKey: ['organization-subscription'],
    queryFn: organizationApi.subscription,
  })
  const { data: payments } = useQuery({
    queryKey: ['organization-payments'],
    queryFn: organizationApi.payments,
  })
  if (!sub) return null

  const rows: [string, string][] = [
    [t('sub.usage_doctors'), `${sub.usage.doctors} / ${limitLabel(t, sub.limits.doctors)}`],
    [
      t('sub.usage_support'),
      `${sub.usage.support_users} / ${limitLabel(t, sub.limits.support_users)}`,
    ],
    [t('sub.usage_locations'), `${sub.usage.locations} / ${limitLabel(t, sub.limits.locations)}`],
    [t('sub.col_storage'), limitLabel(t, sub.limits.storage_gb, ' GB')],
  ]

  return (
    <Card>
      <CardHeader title={t('sub.your_plan')} action={<SubscriptionBadge status={sub.status} />} />
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <p className="font-serif text-xl text-tx">{sub.plan.name}</p>
            <p className="text-[13px] text-tx-3">
              {t('sub.f_modules')}:{' '}
              {sub.modules.length
                ? sub.modules.map((m) => t(`sub.module.${m}`)).join(' · ')
                : t('sub.no_modules')}
            </p>
            <p className="text-[13px] text-tx-3">
              {t('sub.f_analytics')}: {t(`sub.tier.${sub.analytics_tier}`)}
            </p>
          </div>
          <div className="text-right">
            {sub.monthly_price && (
              <p className="font-mono text-lg text-tx">
                {fmtUsd(sub.monthly_price)}
                <span className="text-sm text-tx-3">{t('sub.per_month')}</span>
              </p>
            )}
            <p className="text-xs text-tx-3">
              {sub.period_end ? `${t('sub.f_period_end')} ${fmtDate(sub.period_end)} · ` : ''}
              {expiryLabel(t, sub.days_left)}
            </p>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {rows.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-line px-3 py-2">
              <dt className="text-xs text-tx-3">{label}</dt>
              <dd className="font-mono text-sm text-tx">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-tx-3">
          {t('sub.support_hint')} {t('sub.your_plan_desc')}
        </p>
      </div>
      {payments && payments.length > 0 && (
        <div className="border-t border-line">
          <p className="px-5 pt-4 text-[13px] font-semibold text-tx">{t('sub.payments_title')}</p>
          <PaymentsTable payments={payments} />
        </div>
      )}
    </Card>
  )
}

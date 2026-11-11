import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarPlus, Sparkles } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformPlansApi } from '@/api/platform'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input, Select } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import {
  LIMIT_KEYS,
  LIMIT_LABEL,
  expiryLabel,
  fmtUsd,
  limitLabel,
  limitToText,
  renewOneMonth,
  textToLimit,
} from '@/lib/subscriptions'
import {
  ADDON_MODULES,
  type AddonModule,
  type Plan,
  type PlanLimits,
  type Subscription,
} from '@/types'
import { SubscriptionBadge } from './SubscriptionBadge'

/** Platform console: a clinic's plan, modules, paid period and special terms. Activation and
 * renewal are manual (bank transfer), so this is where they are recorded. */
export function SubscriptionCard({ tenantId, onSaved }: { tenantId: string; onSaved: () => void }) {
  const t = useT()
  const { data: sub } = useQuery({
    queryKey: ['platform-subscription', tenantId],
    queryFn: () => platformPlansApi.subscription(tenantId),
  })
  const { data: catalog } = useQuery({
    queryKey: ['platform-plans'],
    queryFn: platformPlansApi.catalog,
  })

  return (
    <Card>
      <CardHeader
        title={t('sub.card_title')}
        action={sub && <SubscriptionBadge status={sub.status} />}
      />
      {sub && catalog ? (
        // Re-mounted whenever the stored subscription changes, so the form starts from it.
        <SubscriptionForm
          key={JSON.stringify(sub)}
          tenantId={tenantId}
          sub={sub}
          plans={catalog.plans}
          onSaved={onSaved}
        />
      ) : (
        <PageLoader />
      )}
    </Card>
  )
}

type LimitText = Record<keyof PlanLimits, string>

function SubscriptionForm({
  tenantId,
  sub,
  plans,
  onSaved,
}: {
  tenantId: string
  sub: Subscription
  plans: Plan[]
  onSaved: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [planCode, setPlanCode] = useState(sub.plan.code)
  const [modules, setModules] = useState<AddonModule[]>(sub.modules)
  const [periodEnd, setPeriodEnd] = useState(sub.period_end ?? '')
  const [noExpiry, setNoExpiry] = useState(sub.period_end === null)
  const [isTrial, setIsTrial] = useState(sub.is_trial)
  const [graceDays, setGraceDays] = useState(String(sub.grace_days))
  const [overrides, setOverrides] = useState<LimitText>(
    () =>
      Object.fromEntries(
        LIMIT_KEYS.map((k) => [k, limitToText(sub.limit_overrides?.[k] ?? null)]),
      ) as LimitText,
  )
  const [priceOverride, setPriceOverride] = useState(sub.price_override ?? '')

  const selectedPlan = plans.find((p) => p.code === planCode) ?? sub.plan
  // A plan already at the operations tier gains nothing from the analytics add-on.
  const analyticsIncluded = selectedPlan.analytics_tier === 'operations'
  const contracted = analyticsIncluded ? modules.filter((m) => m !== 'analytics') : modules
  // An inactive plan is only offered to the clinic already on it.
  const choices = plans.filter((p) => p.active || p.code === sub.plan.code)

  const refresh = (view: Subscription) => {
    qc.setQueryData(['platform-subscription', tenantId], view)
    onSaved()
  }

  const save = useMutation({
    mutationFn: () => {
      const limitOverrides = Object.fromEntries(
        LIMIT_KEYS.map((k) => [k, textToLimit(overrides[k])]),
      ) as unknown as PlanLimits
      return platformPlansApi.updateSubscription(tenantId, {
        plan_code: planCode,
        modules: contracted,
        period_end: noExpiry || !periodEnd ? null : periodEnd,
        is_trial: isTrial,
        grace_days: Number(graceDays),
        limit_overrides: LIMIT_KEYS.some((k) => limitOverrides[k] !== null) ? limitOverrides : null,
        price_override: priceOverride.trim() === '' ? null : priceOverride,
      })
    },
    onSuccess: (view) => {
      toast(t('sub.saved_sub_ok'))
      refresh(view)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const trial = useMutation({
    mutationFn: () => platformPlansApi.startTrial(tenantId, 7),
    onSuccess: (view) => {
      toast(t('sub.trial_started_ok'))
      refresh(view)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  // A new paid-until date is a paid renewal, not a trial any more.
  const setPaidUntil = (date: string) => {
    setPeriodEnd(date)
    setNoExpiry(false)
    setIsTrial(false)
  }

  const toggleModule = (m: AddonModule, on: boolean) =>
    setModules(on ? [...modules, m] : modules.filter((x) => x !== m))

  const usage: [string, number, number | null, string?][] = [
    ['sub.usage_doctors', sub.usage.doctors, sub.limits.doctors],
    ['sub.usage_support', sub.usage.support_users, sub.limits.support_users, 'sub.support_hint'],
    ['sub.usage_locations', sub.usage.locations, sub.limits.locations],
  ]

  return (
    <div className="grid gap-6 p-5 lg:grid-cols-[1fr_280px]">
      <form
        autoComplete="off"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <div className="grid grid-cols-2 gap-4">
          <Select
            label={t('sub.f_plan')}
            value={planCode}
            onChange={(e) => setPlanCode(e.target.value)}
          >
            {choices.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
                {p.monthly_price ? ` · ${fmtUsd(p.monthly_price)}` : ''}
              </option>
            ))}
          </Select>
          <div>
            <Input
              label={t('sub.f_grace')}
              type="number"
              min={0}
              max={60}
              value={graceDays}
              onChange={(e) => setGraceDays(e.target.value)}
              required
            />
            <p className="mt-1 text-xs text-tx-3">{t('sub.f_grace_hint')}</p>
          </div>
          <div>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Input
                  label={t('sub.f_period_end')}
                  type="date"
                  value={noExpiry ? '' : periodEnd}
                  disabled={noExpiry}
                  onChange={(e) => setPaidUntil(e.target.value)}
                />
              </div>
              <Button
                type="button"
                variant="outline"
                title={t('sub.renew_month')}
                onClick={() => setPaidUntil(renewOneMonth(noExpiry ? null : periodEnd, sub.today))}
              >
                <CalendarPlus className="h-4 w-4" />
                {t('sub.renew_month')}
              </Button>
            </div>
            <label className="mt-2 flex items-center gap-2 text-[13px] text-tx-2">
              <Checkbox checked={noExpiry} onChange={(e) => setNoExpiry(e.target.checked)} />
              {t('sub.f_no_expiry')}
            </label>
          </div>
          <div>
            <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
              {t('sub.f_modules')}
            </span>
            <div className="space-y-1.5">
              {ADDON_MODULES.map((m) => {
                const included = m === 'analytics' && analyticsIncluded
                return (
                  <label key={m} className="flex items-center gap-2 text-sm text-tx">
                    <Checkbox
                      checked={contracted.includes(m)}
                      disabled={included}
                      onChange={(e) => toggleModule(m, e.target.checked)}
                    />
                    {t(`sub.module.${m}`)}
                    <span className="font-mono text-xs text-tx-3">
                      {included
                        ? t('sub.analytics_included')
                        : fmtUsd(sub.addon_prices.prices[m])}
                    </span>
                  </label>
                )
              })}
              <p className="pt-1 text-xs text-tx-3">
                {t('sub.f_analytics')}:{' '}
                {t(
                  `sub.tier.${contracted.includes('analytics') ? 'operations' : selectedPlan.analytics_tier}`,
                )}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-line bg-surface-2 p-4">
          <p className="text-[13px] font-semibold text-tx">{t('sub.custom_terms')}</p>
          <p className="mb-3 text-xs text-tx-3">{t('sub.custom_terms_hint')}</p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {LIMIT_KEYS.map((k) => (
              <Input
                key={k}
                label={t(LIMIT_LABEL[k])}
                type="number"
                min={0}
                placeholder={limitLabel(t, selectedPlan.limits[k])}
                value={overrides[k]}
                onChange={(e) => setOverrides({ ...overrides, [k]: e.target.value })}
              />
            ))}
            <Input
              label={t('sub.f_price_override')}
              type="number"
              min={0}
              step="0.01"
              placeholder={fmtUsd(selectedPlan.monthly_price) ?? t('sub.custom_quote')}
              value={priceOverride}
              onChange={(e) => setPriceOverride(e.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            loading={trial.isPending}
            onClick={() => trial.mutate()}
          >
            <Sparkles className="h-4 w-4" />
            {t('sub.start_trial')}
          </Button>
          <Button type="submit" loading={save.isPending}>
            {t('app.save')}
          </Button>
        </div>
      </form>

      <aside className="space-y-4 rounded-lg border border-line p-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-tx-3">{t('sub.f_period_end')}</p>
          <p className="text-sm font-medium text-tx">
            {sub.period_end ? fmtDate(sub.period_end) : t('sub.no_expiry')}
            {sub.is_trial && (
              <span className="ml-1.5 text-xs text-info">({t('sub.trial_badge')})</span>
            )}
          </p>
          <p className="text-xs text-tx-3">{expiryLabel(t, sub.days_left)}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-tx-3">{t('sub.monthly')}</p>
          <p className="font-mono text-lg text-tx">
            {sub.monthly_price
              ? `${fmtUsd(sub.monthly_price)}${t('sub.per_month')}`
              : t('sub.custom_quote')}
          </p>
        </div>
        <div>
          <p className="mb-1.5 text-xs uppercase tracking-wide text-tx-3">{t('sub.usage')}</p>
          <ul className="space-y-1.5">
            {usage.map(([label, used, limit, hint]) => (
              <li
                key={label}
                className="flex items-center justify-between text-sm"
                title={hint && t(hint)}
              >
                <span className="text-tx-2">{t(label)}</span>
                <span
                  className={
                    limit !== null && used > limit ? 'font-mono text-danger' : 'font-mono text-tx'
                  }
                >
                  {used} / {limitLabel(t, limit)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  )
}

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformPlansApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import {
  LIMIT_KEYS,
  LIMIT_LABEL,
  fmtUsd,
  limitLabel,
  limitToText,
  textToLimit,
} from '@/lib/subscriptions'
import {
  ADDON_MODULES,
  ANALYTICS_TIERS,
  type AddonModule,
  type AddonPricing,
  type AnalyticsTier,
  type Plan,
  type PlanFeature,
  type PlanLimits,
} from '@/types'

const CATALOG_KEY = ['platform-plans']

export function PlansPage() {
  const t = useT()
  const [editing, setEditing] = useState<Plan | null>(null)
  const { data, isLoading } = useQuery({ queryKey: CATALOG_KEY, queryFn: platformPlansApi.catalog })

  if (isLoading || !data) return <PageLoader />

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('sub.plans_title')} />
      <p className="-mt-2 text-[13px] text-tx-3">{t('sub.plans_desc')}</p>

      <Card>
        <Table>
          <thead>
            <Tr>
              <Th>{t('sub.col_plan')}</Th>
              <Th>{t('sub.col_price')}</Th>
              <Th>{t('sub.col_doctors')}</Th>
              <Th>{t('sub.col_support')}</Th>
              <Th>{t('sub.col_locations')}</Th>
              <Th>{t('sub.col_storage')}</Th>
              <Th>{t('sub.col_analytics')}</Th>
              <Th>{t('sub.col_features')}</Th>
              <Th />
            </Tr>
          </thead>
          <tbody>
            {data.plans.map((p) => (
              <Tr key={p.code}>
                <Td>
                  <p className="font-medium text-tx">{p.name}</p>
                  <p className="font-mono text-xs text-tx-3">{p.code}</p>
                </Td>
                <Td className="font-mono">
                  {p.monthly_price === null
                    ? t('sub.custom_quote')
                    : `${fmtUsd(p.monthly_price)}${t('sub.per_month')}`}
                </Td>
                <Td>{limitLabel(t, p.limits.doctors)}</Td>
                <Td>{limitLabel(t, p.limits.support_users)}</Td>
                <Td>{limitLabel(t, p.limits.locations)}</Td>
                <Td>{limitLabel(t, p.limits.storage_gb, ' GB')}</Td>
                <Td>{t(`sub.tier.${p.analytics_tier}`)}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {p.features.map((f) => (
                      <Badge key={f} tone="accent">
                        {t(`sub.feature.${f}`)}
                      </Badge>
                    ))}
                    {!p.active && <Badge>{t('sub.inactive')}</Badge>}
                  </div>
                </Td>
                <Td className="text-right">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(p)}>
                    <Pencil className="h-3.5 w-3.5" />
                    {t('app.edit')}
                  </Button>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <AddonPricingCard key={JSON.stringify(data.addons)} pricing={data.addons} />

      {editing && <PlanModal key={editing.code} plan={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function AddonPricingCard({ pricing }: { pricing: AddonPricing }) {
  const t = useT()
  const qc = useQueryClient()
  const [prices, setPrices] = useState<Record<AddonModule, string>>(pricing.prices)
  const [bundle, setBundle] = useState(pricing.bundle_price)

  const save = useMutation({
    mutationFn: () => platformPlansApi.updateAddons({ prices, bundle_price: bundle }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CATALOG_KEY })
      toast(t('sub.addons_saved_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const dirty =
    bundle !== pricing.bundle_price || ADDON_MODULES.some((m) => prices[m] !== pricing.prices[m])

  return (
    <Card>
      <CardHeader title={t('sub.addons_title')} />
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <p className="text-[13px] text-tx-3">{t('sub.addons_desc')}</p>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          {ADDON_MODULES.map((m) => (
            <Input
              key={m}
              label={t(`sub.module.${m}`)}
              type="number"
              min={0}
              step="0.01"
              suffix="USD"
              value={prices[m]}
              onChange={(e) => setPrices({ ...prices, [m]: e.target.value })}
              required
            />
          ))}
          <Input
            label={t('sub.bundle')}
            type="number"
            min={0}
            step="0.01"
            suffix="USD"
            value={bundle}
            onChange={(e) => setBundle(e.target.value)}
            required
          />
        </div>
        <div className="flex justify-end">
          <Button type="submit" loading={save.isPending} disabled={!dirty}>
            {t('app.save')}
          </Button>
        </div>
      </form>
    </Card>
  )
}

const PLAN_FEATURES: PlanFeature[] = ['user_permissions', 'custom_note_templates']

type LimitText = Record<keyof PlanLimits, string>

function PlanModal({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const [name, setName] = useState(plan.name)
  const [price, setPrice] = useState(plan.monthly_price ?? '')
  const [limits, setLimits] = useState<LimitText>(
    () => Object.fromEntries(LIMIT_KEYS.map((k) => [k, limitToText(plan.limits[k])])) as LimitText,
  )
  const [features, setFeatures] = useState<PlanFeature[]>(plan.features)
  const [active, setActive] = useState(plan.active)
  const [tier, setTier] = useState<AnalyticsTier>(plan.analytics_tier)

  const save = useMutation({
    mutationFn: () =>
      platformPlansApi.update(plan.code, {
        name,
        monthly_price: price.trim() === '' ? null : price,
        limits: Object.fromEntries(
          LIMIT_KEYS.map((k) => [k, textToLimit(limits[k])]),
        ) as unknown as PlanLimits,
        features,
        active,
        analytics_tier: tier,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CATALOG_KEY })
      toast(t('sub.saved_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open onClose={onClose} title={`${t('sub.edit_plan')} · ${plan.name}`} width="max-w-lg">
      <form
        autoComplete="off"
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('sub.f_name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <div>
            <Input
              label={t('sub.f_price')}
              type="number"
              min={0}
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
            <p className="mt-1 text-xs text-tx-3">{t('sub.f_price_hint')}</p>
          </div>
          {LIMIT_KEYS.map((k) => (
            <Input
              key={k}
              label={t(LIMIT_LABEL[k])}
              type="number"
              min={0}
              suffix={k === 'storage_gb' ? 'GB' : undefined}
              placeholder={t('sub.unlimited')}
              value={limits[k]}
              onChange={(e) => setLimits({ ...limits, [k]: e.target.value })}
            />
          ))}
        </div>
        <p className="text-xs text-tx-3">{t('sub.limit_hint')}</p>
        <div>
          <Select
            label={t('sub.f_analytics')}
            value={tier}
            onChange={(e) => setTier(e.target.value as AnalyticsTier)}
          >
            {ANALYTICS_TIERS.map((x) => (
              <option key={x} value={x}>
                {t(`sub.tier.${x}`)}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-tx-3">{t(`sub.tier_desc.${tier}`)}</p>
        </div>
        {PLAN_FEATURES.map((f) => (
          <label key={f} className="flex items-center gap-2 text-sm text-tx">
            <Checkbox
              checked={features.includes(f)}
              onChange={(e) =>
                setFeatures((cur) => (e.target.checked ? [...cur, f] : cur.filter((x) => x !== f)))
              }
            />
            {t(`sub.feature.${f}`)}
          </label>
        ))}
        <label className="flex items-center gap-2 text-sm text-tx">
          <Checkbox checked={active} onChange={(e) => setActive(e.target.checked)} />
          {t('sub.f_active')}
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!name.trim()}>
            {t('app.save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

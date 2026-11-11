import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, Gauge, Search, Wallet, Banknote } from 'lucide-react'
import { platformTenantsApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { WeeklyBars } from '@/components/platform/WeeklyBars'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader } from '@/components/ui/Card'
import { Select } from '@/components/ui/Input'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { cn } from '@/lib/cn'
import { fmtDate, fmtRelative } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { SUBSCRIPTION_TONE, expiryLabel, fmtUsd, limitLabel } from '@/lib/subscriptions'
import { ADDON_MODULES, type ClinicBusiness, type ClinicStanding } from '@/types'

const STANDINGS: ClinicStanding[] = [
  'active',
  'grace',
  'trial',
  'read_only',
  'complimentary',
  'suspended',
]

function StandingBadge({ standing }: { standing: ClinicStanding }) {
  const t = useT()
  if (standing === 'complimentary')
    return <Badge className="whitespace-nowrap">{t('biz.standing.complimentary')}</Badge>
  if (standing === 'suspended') return <Badge tone="danger">{t('biz.standing.suspended')}</Badge>
  return <Badge tone={SUBSCRIPTION_TONE[standing]}>{t(`sub.status.${standing}`)}</Badge>
}

function Seats({ clinic }: { clinic: ClinicBusiness }) {
  const t = useT()
  const seats = [
    ['doctors', 'biz.seat_doctors'],
    ['support_users', 'biz.seat_support'],
    ['locations', 'biz.seat_locations'],
  ] as const
  return (
    <div className="space-y-0.5 text-xs">
      {seats.map(([key, label]) => (
        <p
          key={key}
          className={cn(
            'whitespace-nowrap font-mono',
            clinic.at_capacity.includes(key) ? 'font-semibold text-warn' : 'text-tx-2',
          )}
        >
          <span className="font-sans text-tx-3">{t(label)}</span> {clinic.usage[key]}/
          {limitLabel(t, clinic.limits[key])}
        </p>
      ))}
    </div>
  )
}

export function BusinessPage() {
  const t = useT()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [standing, setStanding] = useState<'all' | ClinicStanding>('all')
  const [offset, setOffset] = useState(0)
  const { data, isLoading } = useQuery({
    queryKey: ['platform-business'],
    queryFn: platformTenantsApi.business,
  })

  const visible = useMemo(() => {
    const term = q.trim().toLowerCase()
    return (data?.clinics ?? []).filter(
      (c) =>
        (standing === 'all' || c.standing === standing) &&
        (!term || c.legal_name.toLowerCase().includes(term) || c.slug.includes(term)),
    )
  }, [data, q, standing])

  if (isLoading || !data) return <PageLoader />

  const open = (id: string) => navigate(`/platform/clinics/${id}`)
  const working = data.clinics.filter((c) => c.standing !== 'suspended').length
  const paged = visible.slice(offset, offset + PAGE_SIZE)
  const monthly = (c: ClinicBusiness) =>
    c.paying ? (
      (fmtUsd(c.monthly) ?? t('sub.custom_quote'))
    ) : (
      <span className="font-sans text-tx-3">{t('biz.no_charge')}</span>
    )

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('biz.title')} />
      <p className="-mt-2 text-[13px] text-tx-3">{t('biz.subtitle')}</p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <div title={t('biz.mrr_hint')}>
          <StatCard icon={Wallet} label={t('biz.mrr')} value={fmtUsd(data.mrr) ?? '$0'} />
          {data.unpriced > 0 && (
            <p className="mt-1 px-1 text-xs text-warn">
              {t('biz.unpriced').replace('{n}', String(data.unpriced))}
            </p>
          )}
        </div>
        <div>
          <StatCard
            icon={Banknote}
            label={t('biz.collected')}
            value={fmtUsd(data.collected_this_month) ?? '$0'}
          />
          <p className="mt-1 px-1 text-xs text-tx-3">
            {t('biz.collected_prev').replace('{amount}', fmtUsd(data.collected_last_month) ?? '$0')}
          </p>
        </div>
        <StatCard
          icon={Activity}
          label={t('biz.active')}
          value={String(data.active_clinics)}
          unit={t('biz.active_of').replace('{n}', String(working))}
        />
        <div title={t('biz.inactive_hint')}>
          <StatCard
            icon={AlertTriangle}
            label={t('biz.inactive')}
            value={String(data.inactive_clinics)}
          />
          <p className="mt-1 px-1 text-xs text-tx-3">{t('biz.inactive_hint')}</p>
        </div>
        <div>
          <StatCard
            icon={Gauge}
            label={t('biz.capacity')}
            value={String(data.at_capacity_clinics)}
          />
          <p className="mt-1 px-1 text-xs text-tx-3">{t('biz.capacity_hint')}</p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_2fr]">
        <Card>
          <CardHeader title={t('biz.by_standing')} />
          <ul className="divide-y divide-line-soft">
            {STANDINGS.filter((s) => data.by_standing[s]).map((s) => (
              <li key={s}>
                <button
                  className="flex w-full items-center justify-between px-5 py-2.5 text-left hover:bg-surface-2/60"
                  onClick={() => {
                    setStanding(s)
                    setOffset(0)
                  }}
                >
                  <StandingBadge standing={s} />
                  <span className="font-mono text-sm text-tx">{data.by_standing[s]}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader title={t('biz.expiring')} />
          {data.expiring.length === 0 ? (
            <p className="px-5 py-6 text-sm text-tx-3">{t('biz.expiring_empty')}</p>
          ) : (
            <Table>
              <tbody>
                {data.expiring.map((c) => (
                  <Tr
                    key={c.tenant_id}
                    className="cursor-pointer"
                    onClick={() => open(c.tenant_id)}
                  >
                    <Td>
                      <p className="font-medium text-tx">{c.legal_name}</p>
                      <p className="text-xs text-tx-3">{c.plan_name}</p>
                    </Td>
                    <Td>
                      <StandingBadge standing={c.standing} />
                    </Td>
                    <Td>
                      <p className="text-sm text-tx">{fmtDate(c.period_end)}</p>
                      <p
                        className={cn(
                          'text-xs',
                          (c.days_left ?? 0) < 0 ? 'text-danger' : 'text-tx-3',
                        )}
                      >
                        {expiryLabel(t, c.days_left)}
                      </p>
                    </Td>
                    <Td className="whitespace-nowrap text-right font-mono">{monthly(c)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader title={t('biz.trend')} />
          <div className="p-5 pt-8">
            <WeeklyBars weeks={data.weekly_signed} />
            <p className="mt-3 text-xs text-tx-3">{t('biz.trend_desc')}</p>
          </div>
        </Card>

        <Card>
          <CardHeader title={t('biz.plans')} />
          <Table>
            <thead>
              <Tr>
                <Th>{t('biz.col_plan')}</Th>
                <Th className="text-right">{t('biz.col_clinics')}</Th>
                <Th className="text-right">{t('biz.col_mrr')}</Th>
              </Tr>
            </thead>
            <tbody>
              {data.by_plan.map((p) => (
                <Tr key={p.code}>
                  <Td className="text-tx">{p.name}</Td>
                  <Td className="text-right font-mono">{p.clinics}</Td>
                  <Td className="text-right font-mono">{fmtUsd(p.mrr)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <div className="border-t border-line px-5 py-3">
            <p className="mb-1.5 text-xs uppercase tracking-wide text-tx-3">{t('biz.modules')}</p>
            <ul className="space-y-1 text-sm">
              {ADDON_MODULES.map((m) => (
                <li key={m} className="flex justify-between">
                  <span className="text-tx-2">{t(`sub.module.${m}`)}</span>
                  <span className="font-mono text-tx">{data.by_module[m] ?? 0}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title={t('biz.clinics')} />
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setOffset(0)
              }}
              placeholder={t('biz.search')}
              className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
            />
          </div>
          <Select
            value={standing}
            onChange={(e) => {
              setStanding(e.target.value as 'all' | ClinicStanding)
              setOffset(0)
            }}
          >
            <option value="all">{t('biz.all_standings')}</option>
            {STANDINGS.map((s) => (
              <option key={s} value={s}>
                {s === 'complimentary' || s === 'suspended'
                  ? t(`biz.standing.${s}`)
                  : t(`sub.status.${s}`)}
              </option>
            ))}
          </Select>
        </div>
        <Table>
          <thead>
            <Tr>
              <Th>{t('biz.col_clinic')}</Th>
              <Th>{t('biz.col_standing')}</Th>
              <Th>{t('biz.col_plan')}</Th>
              <Th className="text-right">{t('biz.col_monthly')}</Th>
              <Th>{t('biz.col_expiry')}</Th>
              <Th>{t('biz.col_seats')}</Th>
              <Th>{t('biz.col_activity')}</Th>
              <Th className="whitespace-nowrap text-right">{t('biz.col_signed')}</Th>
            </Tr>
          </thead>
          <tbody>
            {paged.map((c) => (
              <Tr key={c.tenant_id} className="cursor-pointer" onClick={() => open(c.tenant_id)}>
                <Td>
                  <p className="font-medium text-tx">{c.legal_name}</p>
                  <p className="font-mono text-xs text-tx-3">{c.slug}</p>
                </Td>
                <Td>
                  <StandingBadge standing={c.standing} />
                </Td>
                <Td>
                  <p className="text-sm text-tx">{c.plan_name}</p>
                  {c.modules.length > 0 && (
                    <p className="text-xs text-tx-3">
                      {c.modules.map((m) => t(`sub.module.${m}`)).join(', ')}
                    </p>
                  )}
                </Td>
                <Td className="whitespace-nowrap text-right font-mono">{monthly(c)}</Td>
                <Td>
                  <p className="whitespace-nowrap text-sm text-tx">
                    {c.period_end ? fmtDate(c.period_end) : t('sub.no_expiry')}
                  </p>
                  {c.period_end && (
                    <p className="text-xs text-tx-3">{expiryLabel(t, c.days_left)}</p>
                  )}
                </Td>
                <Td>
                  <Seats clinic={c} />
                </Td>
                <Td>
                  {c.last_activity ? (
                    <>
                      <p className="text-sm text-tx">{fmtRelative(c.last_activity)}</p>
                      <p className="whitespace-nowrap text-xs text-tx-3">
                        {t('biz.people').replace('{n}', String(c.active_users))}
                      </p>
                    </>
                  ) : (
                    <span className="text-sm text-warn">{t('biz.no_activity')}</span>
                  )}
                </Td>
                <Td className="text-right font-mono">{c.signed_records}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        {visible.length > PAGE_SIZE && (
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={paged.length}
            total={visible.length}
            onChange={setOffset}
          />
        )}
      </Card>
    </div>
  )
}

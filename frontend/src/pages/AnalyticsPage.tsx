import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { analyticsApi, type AnalyticsOverview } from '@/api/analytics'
import { appointmentsApi } from '@/api/appointments'
import { BreakdownBars } from '@/components/analytics/BreakdownBars'
import { DoctorsTable } from '@/components/analytics/DoctorsTable'
import { Heatmap } from '@/components/analytics/Heatmap'
import { LockedSection } from '@/components/analytics/LockedSection'
import { MetricTiles } from '@/components/analytics/MetricTiles'
import { PageHeader } from '@/components/PageHeader'
import { TrendBars } from '@/components/platform/TrendBars'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Segmented } from '@/components/ui/Segmented'
import { Select } from '@/components/ui/Select'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtIncome, presetParams, type Preset } from '@/lib/analytics'
import { clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

const PRESETS: Preset[] = ['week', 'month', 'last_month', 'last_90', 'range']
const DATE_INPUT =
  'h-9 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none'

/** Practice metrics. What shows depends on the clinic's analytics tier (the backend sends
 * null for sections above it) and on the user's metrics permissions (own or clinic scope,
 * with or without income). */
export function AnalyticsPage() {
  const t = useT()
  const today = clinicToday()
  const clinicScope = useAuthStore((s) => s.can('analytics.clinic'))
  const [preset, setPreset] = useState<Preset>('month')
  const [from, setFrom] = useState(today.slice(0, 8) + '01')
  const [to, setTo] = useState(today)
  const [range, setRange] = useState({ from, to })
  const [doctor, setDoctor] = useState('')

  const params = {
    ...presetParams(preset, today, range.from, range.to),
    ...(doctor ? { doctor_id: doctor } : {}),
  }
  const { data, error, isLoading } = useQuery({
    queryKey: ['analytics', params],
    queryFn: () => analyticsApi.overview(params),
    placeholderData: keepPreviousData,
  })
  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: appointmentsApi.bookingOptions,
    enabled: clinicScope,
  })

  if (isLoading) return <PageLoader />
  if (error || !data) {
    return <p className="p-8 text-sm text-danger">{errorMessage(error)}</p>
  }

  const basic = data.tier === 'basic'
  const compareLabel = t('an.compared')
    .replace('{from}', fmtDate(data.period.previous_start, 'd MMM'))
    .replace('{to}', fmtDate(data.period.previous_end, 'd MMM'))

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        eyebrow={`${fmtDate(data.period.start, 'd MMM yyyy')} – ${fmtDate(data.period.end, 'd MMM yyyy')}`}
        title={t('an.title')}
      />
      <p className="-mt-3 text-[13px] text-tx-3">
        {t(data.scope === 'clinic' ? 'an.subtitle_clinic' : 'an.subtitle_own')}
      </p>

      {basic ? (
        <p className="text-[13px] text-tx-3">{t('an.basic_period')}</p>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Segmented
            value={preset}
            onChange={setPreset}
            options={PRESETS.map((p) => ({ value: p, label: t(`an.period.${p}`) }))}
          />
          {preset === 'range' && (
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                setRange({ from, to })
              }}
            >
              <label className="text-[13px] text-tx-3">{t('an.from')}</label>
              <input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                className={DATE_INPUT}
              />
              <label className="text-[13px] text-tx-3">{t('an.to')}</label>
              <input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className={DATE_INPUT}
              />
              <Button type="submit" size="sm" variant="outline">
                {t('an.apply')}
              </Button>
            </form>
          )}
          {clinicScope && options && (
            <div className="ml-auto w-56">
              <Select value={doctor} onChange={(e) => setDoctor(e.target.value)}>
                <option value="">{t('an.all_doctors')}</option>
                {options.doctors.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
        </div>
      )}

      <p className="-mb-3 text-xs text-tx-3">{compareLabel}</p>
      <MetricTiles
        current={data.current}
        previous={data.previous}
        money={data.money}
        compareLabel={t('an.vs_previous')}
      />

      {data.doctors && (
        <Card>
          <CardHeader title={t('an.doctors_title')} />
          <DoctorsTable rows={data.doctors} money={data.money} />
        </Card>
      )}

      {data.trend ? <TrendSection data={data} /> : <LockedSection tier="clinic" />}

      {data.types && data.insurers && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title={t('an.types_title')} />
            <BreakdownBars
              items={data.types.map((b) => ({
                key: b.key ?? '',
                label: t(`apptype.${b.key}`),
                count: b.attended,
                income: b.income,
              }))}
            />
          </Card>
          <Card>
            <CardHeader title={t('an.insurers_title')} />
            <BreakdownBars
              items={data.insurers.map((b) => ({
                key: b.key ?? 'private',
                label: b.key ? (b.label ?? '—') : t('an.private'),
                count: b.attended,
                income: b.income,
              }))}
            />
          </Card>
        </div>
      )}

      {data.operations ? (
        <OperationsSection data={data} />
      ) : (
        data.trend && <LockedSection tier="operations" />
      )}
    </div>
  )
}

function TrendSection({ data }: { data: AnalyticsOverview }) {
  const t = useT()
  const [asTable, setAsTable] = useState(false)
  const trend = data.trend ?? []
  const point = (week: string, value: string) =>
    t('an.trend_point').replace('{date}', fmtDate(week, 'd MMM')).replace('{value}', value)
  const toggle = (
    <button
      type="button"
      className="text-xs text-accent hover:underline"
      onClick={() => setAsTable(!asTable)}
    >
      {asTable ? t('an.chart_view') : t('an.table_view')}
    </button>
  )

  if (asTable) {
    return (
      <Card>
        <CardHeader title={t('an.trend_attended')} action={toggle} />
        <Table>
          <thead>
            <Tr>
              <Th>{t('an.col_week')}</Th>
              <Th className="text-right">{t('an.attended')}</Th>
              {data.money && <Th className="text-right">{t('an.income')}</Th>}
            </Tr>
          </thead>
          <tbody>
            {trend.map((w) => (
              <Tr key={w.week}>
                <Td>{fmtDate(w.week, 'd MMM yyyy')}</Td>
                <Td className="text-right font-mono">{w.attended}</Td>
                {data.money && <Td className="text-right font-mono">{fmtIncome(w.income)}</Td>}
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>
    )
  }

  return (
    <div className={data.money ? 'grid grid-cols-1 gap-6 lg:grid-cols-2' : ''}>
      <Card>
        <CardHeader title={t('an.trend_attended')} action={toggle} />
        <div className="p-5">
          <TrendBars
            points={trend.map((w) => ({
              date: w.week,
              count: w.attended,
              label: point(w.week, String(w.attended)),
            }))}
          />
        </div>
      </Card>
      {data.money && (
        <Card>
          <CardHeader title={t('an.trend_income')} />
          <div className="p-5">
            <TrendBars
              valueFormat={fmtIncome}
              points={trend.map((w) => ({
                date: w.week,
                count: Number(w.income ?? 0),
                label: point(w.week, fmtIncome(w.income)),
              }))}
            />
          </div>
        </Card>
      )}
    </div>
  )
}

function OperationsSection({ data }: { data: AnalyticsOverview }) {
  const t = useT()
  const ops = data.operations!
  const modules = (['vaccinations', 'applications', 'procedures'] as const).filter(
    (m) => ops.modules[m] !== null,
  )
  return (
    <>
      <Card>
        <CardHeader title={t('an.heatmap_title')} />
        <Heatmap cells={ops.heatmap} />
      </Card>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title={t('an.lead_title')} />
          <BreakdownBars
            items={Object.entries(ops.lead_times).map(([k, n]) => ({
              key: k,
              label: t(`an.lead.${k}`),
              count: n,
            }))}
          />
        </Card>
        <Card>
          <CardHeader title={t('an.patients_title')} />
          <BreakdownBars
            items={[
              { key: 'first', label: t('an.first_time'), count: data.current.new_patients },
              { key: 'returning', label: t('an.returning'), count: ops.returning_patients },
            ]}
          />
        </Card>
        {modules.length > 0 && (
          <Card>
            <CardHeader title={t('an.modules_title')} />
            <dl className="divide-y divide-line-soft">
              {modules.map((m) => (
                <div key={m} className="flex items-center justify-between px-5 py-3">
                  <dt className="text-[13px] text-tx-2">{t(`an.mod.${m}`)}</dt>
                  <dd className="font-mono text-sm text-tx">{ops.modules[m]}</dd>
                </div>
              ))}
            </dl>
          </Card>
        )}
      </div>
    </>
  )
}

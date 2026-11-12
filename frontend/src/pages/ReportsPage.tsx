import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import {
  addDays,
  endOfMonth,
  endOfWeek,
  format,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from 'date-fns'
import { Download } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import {
  reportsApi,
  type ReportCell,
  type ReportColumn,
  type ReportKind,
  type ReportParams,
  type ReportTable,
} from '@/api/reports'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Pager } from '@/components/ui/Pager'
import { Segmented } from '@/components/ui/Segmented'
import { Select } from '@/components/ui/Select'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtFee } from '@/lib/fees'
import { clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import type { Permission } from '@/types'

type Preset = 'week' | 'month' | 'last_month' | 'last_90' | 'range'

const PRESETS: Preset[] = ['week', 'month', 'last_month', 'last_90', 'range']
const BASIC_PRESETS: Preset[] = ['month', 'last_month']
const PAGE = 50
const DATE_INPUT =
  'h-9 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none'

/** Each report and, for the module ones, the permission that only exists with the module. */
const KINDS: { kind: ReportKind; needs?: Permission; money?: boolean }[] = [
  { kind: 'appointments' },
  { kind: 'income', money: true },
  { kind: 'insurers' },
  { kind: 'no_shows' },
  { kind: 'vaccinations', needs: 'vaccinations.view' },
  { kind: 'procedures', needs: 'procedures.view' },
  { kind: 'applications', needs: 'applications.view' },
]

const ENUM_PREFIX: Record<string, string> = {
  appointment_type: 'apptype',
  appointment_status: 'status',
  sex: 'sex',
  application_route: 'apl.route',
  income_source: 'rep.source',
}

const iso = (d: Date) => format(d, 'yyyy-MM-dd')

/** The full calendar span a preset stands for (a report lists upcoming appointments too). */
function presetRange(preset: Preset, today: string, from: string, to: string) {
  const day = parseISO(today)
  switch (preset) {
    case 'week':
      return {
        start: iso(startOfWeek(day, { weekStartsOn: 1 })),
        end: iso(endOfWeek(day, { weekStartsOn: 1 })),
      }
    case 'month':
      return { start: iso(startOfMonth(day)), end: iso(endOfMonth(day)) }
    case 'last_month': {
      const prev = subMonths(day, 1)
      return { start: iso(startOfMonth(prev)), end: iso(endOfMonth(prev)) }
    }
    case 'last_90':
      return { start: iso(addDays(day, -89)), end: today }
    case 'range':
      return { start: from, end: to }
  }
}

function useCell() {
  const t = useT()
  return (column: ReportColumn, value: ReportCell): string => {
    if (value === null) {
      if (column.key === 'insurer') return t('rep.no_insurer')
      return column.kind === 'dose' ? t('rep.outside_scheme') : '—'
    }
    if (column.kind === 'vaccine') {
      const name = t(`vax.name.${value}`)
      return name.startsWith('vax.name.') ? String(value) : name
    }
    if (column.kind === 'dose') {
      const [kind, n = ''] = String(value).split(':')
      return t(`vax.kind.${kind}`).replace('{n}', n)
    }
    if (column.kind === 'date') return fmtDate(String(value))
    if (column.kind === 'money') return fmtFee(String(value)) ?? '—'
    if (column.kind === 'bool') return t(value ? 'rep.yes' : 'rep.no')
    if (column.kind === 'age') {
      const months = Number(value)
      return months < 24
        ? t('rep.age_months').replace('{n}', String(months))
        : t('rep.age_years').replace('{n}', String(Math.floor(months / 12)))
    }
    if (column.kind.startsWith('enum:')) {
      const prefix = ENUM_PREFIX[column.kind.slice(5)]
      return prefix ? t(`${prefix}.${value}`) : String(value)
    }
    return String(value)
  }
}

const NUMERIC = new Set(['money', 'count'])

function DataTable({ table, totals }: { table: ReportTable; totals?: boolean }) {
  const t = useT()
  const cell = useCell()
  const sums = table.columns.map((c, i) =>
    NUMERIC.has(c.kind) ? table.rows.reduce((acc, r) => acc + Number(r[i] ?? 0), 0) : null,
  )
  return (
    <Table>
      <thead>
        <tr>
          {table.columns.map((c) => (
            <Th key={c.key} className={cn(NUMERIC.has(c.kind) && 'text-right')}>
              {t(`rep.col.${c.key}`)}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.rows.map((row, i) => (
          <Tr key={i}>
            {table.columns.map((c, j) => (
              <Td
                key={c.key}
                className={cn(
                  'whitespace-nowrap',
                  NUMERIC.has(c.kind) && 'text-right tabular-nums',
                  c.key === 'patient' && 'font-medium text-tx',
                )}
              >
                {cell(c, row[j])}
              </Td>
            ))}
          </Tr>
        ))}
        {totals && table.rows.length > 1 && (
          <tr className="font-semibold text-tx">
            {table.columns.map((c, j) => (
              <Td
                key={c.key}
                className={cn('text-tx', NUMERIC.has(c.kind) && 'text-right tabular-nums')}
              >
                {j === 0
                  ? t('rep.total')
                  : sums[j] === null
                    ? ''
                    : c.kind === 'money'
                      ? fmtFee(String(sums[j]))
                      : sums[j]}
              </Td>
            ))}
          </tr>
        )}
      </tbody>
    </Table>
  )
}

/** Reports: the rows behind the metrics, with the same scope and money rules, to read on
 * screen or download as CSV (audited). */
export function ReportsPage() {
  const t = useT()
  const lang = useUIStore((s) => s.lang)
  const today = clinicToday()
  const can = useAuthStore((s) => s.can)
  const clinicScope = can('analytics.clinic')
  const canExport = can('reports.export')
  const money = can('analytics.money')
  const kinds = KINDS.filter((k) => (!k.needs || can(k.needs)) && (!k.money || money))
  const [kind, setKind] = useState<ReportKind>('appointments')
  const [preset, setPreset] = useState<Preset>('month')
  const [from, setFrom] = useState(today.slice(0, 8) + '01')
  const [to, setTo] = useState(today)
  const [range, setRange] = useState({ from, to })
  const [doctor, setDoctor] = useState('')
  const [offset, setOffset] = useState(0)

  const params: ReportParams = {
    ...presetRange(preset, today, range.from, range.to),
    ...(doctor ? { doctor_id: doctor } : {}),
  }
  const { data, error, isLoading, isFetching } = useQuery({
    queryKey: ['report', kind, params],
    queryFn: () => reportsApi.get(kind, params),
    placeholderData: keepPreviousData,
    retry: false,
  })
  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: appointmentsApi.bookingOptions,
    enabled: clinicScope,
  })
  const exportCsv = useMutation({
    mutationFn: (part: 'detail' | 'summary') =>
      reportsApi.download(
        kind,
        { ...params, part, lang },
        `medicore-${kind}${part === 'summary' ? '-' + t('rep.summary').toLowerCase() : ''}-${params.start}-${params.end}.csv`,
      ),
    onSuccess: () => toast(t('rep.exported')),
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const basic = data?.tier === 'basic'
  const presets = basic ? BASIC_PRESETS : PRESETS
  const pick = (next: ReportKind) => {
    setKind(next)
    setOffset(0)
  }
  const detailPage: ReportTable | null = data
    ? { columns: data.detail.columns, rows: data.detail.rows.slice(offset, offset + PAGE) }
    : null

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        eyebrow={`${fmtDate(params.start, 'd MMM yyyy')} – ${fmtDate(params.end, 'd MMM yyyy')}`}
        title={t('rep.title')}
      />
      <p className="-mt-3 text-[13px] text-tx-3">
        {t(clinicScope ? 'rep.subtitle_clinic' : 'rep.subtitle_own')}
      </p>

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <nav className="space-y-1">
          {kinds.map((k) => (
            <button
              key={k.kind}
              onClick={() => pick(k.kind)}
              className={cn(
                'w-full rounded-lg px-3 py-2.5 text-left transition-colors',
                kind === k.kind ? 'bg-[var(--accent-10)]' : 'hover:bg-surface-2',
              )}
            >
              <span
                className={cn(
                  'block text-sm font-medium',
                  kind === k.kind ? 'text-accent' : 'text-tx',
                )}
              >
                {t(`rep.kind.${k.kind}`)}
              </span>
              <span className="mt-0.5 block text-xs text-tx-3">{t(`rep.desc.${k.kind}`)}</span>
            </button>
          ))}
        </nav>

        <div className="min-w-0 space-y-5">
          <div className="flex flex-wrap items-end gap-3">
            <Segmented
              value={presets.includes(preset) ? preset : 'month'}
              onChange={(p) => {
                setPreset(p)
                setOffset(0)
              }}
              options={presets.map((p) => ({ value: p, label: t(`rep.period.${p}`) }))}
            />
            {preset === 'range' && !basic && (
              <form
                className="flex flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  setRange({ from, to })
                  setOffset(0)
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
                <Select
                  value={doctor}
                  onChange={(e) => {
                    setDoctor(e.target.value)
                    setOffset(0)
                  }}
                >
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
          {basic && <p className="text-[13px] text-tx-3">{t('rep.basic_period')}</p>}

          {isLoading ? (
            <PageLoader />
          ) : error || !data ? (
            <p className="text-sm text-danger">{errorMessage(error)}</p>
          ) : (
            <div className={cn('space-y-5', isFetching && 'opacity-60')}>
              <Card>
                <CardHeader
                  title={t('rep.summary')}
                  action={
                    canExport &&
                    data.summary.rows.length > 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        loading={exportCsv.isPending && exportCsv.variables === 'summary'}
                        onClick={() => exportCsv.mutate('summary')}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t('rep.export_summary')}
                      </Button>
                    )
                  }
                />
                {data.summary.rows.length === 0 ? (
                  <p className="px-5 py-6 text-sm text-tx-3">{t('rep.empty')}</p>
                ) : (
                  <DataTable table={data.summary} totals />
                )}
              </Card>

              <Card>
                <CardHeader
                  title={
                    <>
                      {t('rep.detail')}{' '}
                      <span className="font-normal text-tx-3">
                        · {t('rep.rows').replace('{n}', String(data.detail.rows.length))}
                      </span>
                    </>
                  }
                  action={
                    canExport &&
                    data.detail.rows.length > 0 && (
                      <Button
                        size="sm"
                        loading={exportCsv.isPending && exportCsv.variables === 'detail'}
                        onClick={() => exportCsv.mutate('detail')}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t('rep.export')}
                      </Button>
                    )
                  }
                />
                {data.detail.rows.length === 0 ? (
                  <p className="px-5 py-6 text-sm text-tx-3">{t('rep.empty')}</p>
                ) : (
                  <>
                    <DataTable table={detailPage!} />
                    {data.detail.rows.length > PAGE && (
                      <Pager
                        offset={offset}
                        limit={PAGE}
                        count={detailPage!.rows.length}
                        total={data.detail.rows.length}
                        onChange={setOffset}
                      />
                    )}
                  </>
                )}
              </Card>
              {canExport && <p className="text-xs text-tx-3">{t('rep.export_hint')}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

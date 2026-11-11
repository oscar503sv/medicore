import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  Copy,
  Database,
  KeyRound,
  Lock,
  RefreshCw,
  Server,
  ServerCrash,
  ShieldAlert,
  Timer,
  Users,
} from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformTenantsApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { TrendBars } from '@/components/platform/TrendBars'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Pager } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtBytes, fmtDate, fmtDateTime, fmtDuration, fmtRelative, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { ConsoleLogin, JobState, Performance, ScheduledJob, SystemStatus } from '@/types'
import type { Tone } from '@/components/ui/badgeTone'

const REFRESH_MS = 60_000
const ERRORS_PAGE = 20

/** One fact of the status strip: an icon, a label, a value and a quieter detail line. */
function Fact({
  icon: Icon,
  label,
  value,
  detail,
  ok,
}: {
  icon: typeof Server
  label: string
  value: string
  detail?: string | string[]
  ok?: boolean
}) {
  return (
    <div className="flex min-w-0 items-start gap-3 px-5 py-4">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-tx-3" />
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wider text-tx-3">{label}</p>
        <p className="mt-0.5 flex items-center gap-1.5 truncate text-sm font-medium text-tx">
          {ok !== undefined && (
            <span className={cn('h-2 w-2 shrink-0 rounded-full', ok ? 'bg-ok' : 'bg-danger')} />
          )}
          {value}
        </p>
        {(Array.isArray(detail) ? detail : detail ? [detail] : []).map((line) => (
          <p key={line} className="truncate text-xs text-tx-3">
            {line}
          </p>
        ))}
      </div>
    </div>
  )
}

function StatusStrip({ data }: { data: SystemStatus }) {
  const t = useT()
  const { runtime, database } = data
  return (
    <Card className="grid divide-y divide-line-soft sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
      <Fact
        icon={Server}
        label={t('mon.api')}
        value={t('mon.online')}
        ok
        detail={t('mon.uptime').replace('{d}', fmtDuration(runtime.uptime_seconds))}
      />
      <Fact
        icon={Database}
        label={t('mon.database')}
        value={`PostgreSQL ${database.version.split(' ')[0]}`}
        ok
        detail={[
          t('mon.latency').replace('{ms}', String(database.latency_ms)),
          t('mon.connections')
            .replace('{n}', String(database.connections.total))
            .replace('{max}', String(database.connections.max_connections)),
        ]}
      />
      <Fact
        icon={KeyRound}
        label={t('mon.version')}
        value={`${runtime.version} · ${runtime.environment}`}
        detail={runtime.commit ? runtime.commit.slice(0, 12) : t('mon.no_commit')}
      />
      <Fact
        icon={Database}
        label={t('mon.migration')}
        value={database.revision ?? '—'}
        detail={`${t('mon.db_size')}: ${fmtBytes(database.size_bytes)}`}
      />
    </Card>
  )
}

const shortCommit = (c: string | null) => (c ? c.slice(0, 7) : '—')

/** "Firefox", "Chrome"… from a user agent; the full string goes in the tooltip. */
function browserName(ua: string | null): string {
  if (!ua) return '—'
  for (const [needle, name] of [
    ['Edg/', 'Edge'],
    ['Firefox/', 'Firefox'],
    ['Chrome/', 'Chrome'],
    ['Safari/', 'Safari'],
  ] as const) {
    if (ua.includes(needle)) return name
  }
  return ua.slice(0, 24)
}

const JOB_TONE: Record<JobState, Tone> = {
  ok: 'ok',
  failed: 'danger',
  overdue: 'warn',
  never: 'neutral',
}

const LOGIN_TONE: Record<ConsoleLogin['action'], Tone> = {
  'auth.platform_login': 'ok',
  'auth.platform_login_failed': 'warn',
  'auth.platform_login_locked': 'danger',
}

function ConsoleLogins({ logins }: { logins: ConsoleLogin[] }) {
  const t = useT()
  return (
    <Card>
      <CardHeader title={t('mon.console_logins')} />
      {logins.length === 0 ? (
        <p className="px-5 py-6 text-sm text-tx-3">{t('mon.console_empty')}</p>
      ) : (
        <ul className="divide-y divide-line-soft">
          {logins.map((l, i) => (
            <li
              key={`${l.at}-${i}`}
              className="flex items-center justify-between gap-3 px-5 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-sm text-tx">{l.admin_name ?? '—'}</p>
                <p className="truncate text-xs text-tx-3" title={l.user_agent ?? undefined}>
                  {fmtRelative(l.at)} · {l.ip_address ?? '—'} · {browserName(l.user_agent)}
                </p>
              </div>
              <Badge tone={LOGIN_TONE[l.action]}>{t(`mon.login.${l.action}`)}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function ScheduledJobs({ jobs }: { jobs: ScheduledJob[] }) {
  const t = useT()
  const label = (job: string) => {
    const key = `mon.job.${job}`
    return t(key) === key ? job : t(key)
  }
  return (
    <Card>
      <CardHeader title={t('mon.jobs')} />
      <ul className="divide-y divide-line-soft">
        {jobs.map((j) => (
          <li key={j.job} className="flex items-start justify-between gap-3 px-5 py-3">
            <div className="min-w-0 space-y-0.5">
              <p className="text-sm text-tx">{label(j.job)}</p>
              {j.last_finished_at && j.last_started_at ? (
                <>
                  <p className="text-xs text-tx-3">
                    {t('mon.job_last')
                      .replace('{when}', fmtRelative(j.last_finished_at))
                      .replace(
                        '{dur}',
                        fmtDuration(
                          (Date.parse(j.last_finished_at) - Date.parse(j.last_started_at)) / 1000,
                        ),
                      )}
                    {!j.last_ok && j.last_detail && (
                      <span className="font-mono text-danger"> · {j.last_detail}</span>
                    )}
                  </p>
                  {!j.last_ok && (
                    <p className="text-xs text-tx-3">
                      {t('mon.job_last_ok').replace(
                        '{when}',
                        j.last_success_at ? fmtRelative(j.last_success_at) : '—',
                      )}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-xs text-tx-3">{t('mon.job_never')}</p>
              )}
              {j.expected_every_hours && (
                <p className="text-xs text-tx-4">
                  {t('mon.job_every').replace('{h}', String(Math.round(j.expected_every_hours)))}
                </p>
              )}
            </div>
            <Badge tone={JOB_TONE[j.state]}>{t(`mon.job_state.${j.state}`)}</Badge>
          </li>
        ))}
      </ul>
    </Card>
  )
}

const fmtMs = (ms: number | null) => (ms === null ? '—' : `${Math.round(ms).toLocaleString()} ms`)
const fmtPct = (part: number, whole: number) =>
  whole ? `${((part / whole) * 100).toFixed(part && part / whole < 0.001 ? 2 : 1)}%` : '—'

/** Request volume, latency percentiles, error rates and the slowest routes of the last day. */
function PerformanceSection({ perf }: { perf: Performance }) {
  const t = useT()
  return (
    <div className="space-y-5">
      <h2 className="pt-2 text-sm font-semibold text-tx">{t('mon.perf')}</h2>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div>
          <StatCard
            icon={Activity}
            label={t('mon.perf_requests')}
            value={perf.requests.toLocaleString()}
          />
        </div>
        <div>
          <StatCard icon={Timer} label={t('mon.perf_p50')} value={fmtMs(perf.p50_ms)} />
        </div>
        <div>
          <StatCard icon={Timer} label={t('mon.perf_p95')} value={fmtMs(perf.p95_ms)} />
          <p className="mt-1 px-1 text-xs text-tx-3">{t('mon.perf_p95_hint')}</p>
        </div>
        <div>
          <StatCard
            icon={ServerCrash}
            label={t('mon.perf_5xx')}
            value={fmtPct(perf.server_errors, perf.requests)}
            unit={`(${perf.server_errors})`}
          />
          <p className="mt-1 px-1 text-xs text-tx-3">
            {t('mon.perf_4xx').replace('{pct}', fmtPct(perf.client_errors, perf.requests))}
          </p>
        </div>
      </div>

      <Card>
        <CardHeader title={t('mon.perf_volume')} />
        <div className="p-5 pt-8">
          <TrendBars
            axisFormat="HH:mm"
            points={perf.hourly.map((h) => ({
              date: h.hour,
              count: h.count,
              label: t('mon.perf_hour')
                .replace('{time}', fmtTime(h.hour))
                .replace('{n}', h.count.toLocaleString())
                .replace('{e}', String(h.server_errors)),
            }))}
          />
        </div>
      </Card>

      <Card>
        <CardHeader title={t('mon.perf_slowest')} />
        {perf.slowest.length === 0 ? (
          <p className="px-5 py-6 text-sm text-tx-3">{t('mon.perf_empty')}</p>
        ) : (
          <Table>
            <thead>
              <Tr>
                <Th>{t('mon.col_route')}</Th>
                <Th className="text-right">{t('mon.col_requests')}</Th>
                <Th className="text-right">{t('mon.col_avg')}</Th>
                <Th className="text-right">{t('mon.col_p95')}</Th>
                <Th className="text-right">{t('mon.col_max')}</Th>
                <Th className="text-right">{t('mon.col_errors')}</Th>
              </Tr>
            </thead>
            <tbody>
              {perf.slowest.map((r) => (
                <Tr key={`${r.method} ${r.route}`}>
                  <Td className="font-mono text-xs text-tx-2">
                    <span className="text-tx-3">{r.method}</span> {r.route}
                  </Td>
                  <Td className="text-right font-mono text-sm">{r.count.toLocaleString()}</Td>
                  <Td className="text-right font-mono text-sm">{fmtMs(r.avg_ms)}</Td>
                  <Td className="text-right font-mono text-sm text-tx">{fmtMs(r.p95_ms)}</Td>
                  <Td className="text-right font-mono text-sm text-tx-3">{fmtMs(r.max_ms)}</Td>
                  <Td
                    className={cn(
                      'text-right font-mono text-sm',
                      r.server_errors ? 'text-danger' : 'text-tx-3',
                    )}
                  >
                    {r.client_errors} / {r.server_errors}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
        <p className="border-t border-line px-5 py-3 text-xs text-tx-3">{t('mon.perf_note')}</p>
      </Card>
    </div>
  )
}

function ErrorList({ retentionDays }: { retentionDays: number }) {
  const t = useT()
  const [offset, setOffset] = useState(0)
  const { data } = useQuery({
    queryKey: ['platform-errors', offset],
    queryFn: () => platformTenantsApi.serverErrors(offset, ERRORS_PAGE),
    refetchInterval: REFRESH_MS,
  })
  if (!data || data.total === 0) return null
  return (
    <Card>
      <CardHeader title={t('mon.errors_recent')} />
      <Table>
        <thead>
          <Tr>
            <Th>{t('mon.col_when')}</Th>
            <Th>{t('mon.col_route')}</Th>
            <Th>{t('mon.col_type')}</Th>
            <Th>{t('mon.col_location')}</Th>
            <Th>{t('mon.col_commit')}</Th>
          </Tr>
        </thead>
        <tbody>
          {data.items.map((e) => (
            <Tr key={e.id}>
              <Td className="whitespace-nowrap text-sm text-tx">{fmtDateTime(e.occurred_at)}</Td>
              <Td className="font-mono text-xs text-tx-2">
                <span className="text-tx-3">{e.method}</span> {e.route}
              </Td>
              <Td className="font-mono text-xs text-danger">{e.error_type}</Td>
              <Td className="font-mono text-xs text-tx-3">{e.location}</Td>
              <Td className="font-mono text-xs text-tx-3">{shortCommit(e.commit)}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      {data.total > ERRORS_PAGE && (
        <Pager
          offset={offset}
          limit={ERRORS_PAGE}
          count={data.items.length}
          total={data.total}
          onChange={setOffset}
        />
      )}
      <p className="border-t border-line px-5 py-3 text-xs text-tx-3">
        {t('mon.errors_note').replace('{n}', String(retentionDays))}
      </p>
    </Card>
  )
}

export function MonitoringPage() {
  const t = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data, isLoading, isFetching, dataUpdatedAt, refetch } = useQuery({
    queryKey: ['platform-monitoring'],
    queryFn: platformTenantsApi.monitoring,
    refetchInterval: REFRESH_MS,
  })

  const closeSupport = useMutation({
    mutationFn: ({ tenantId, sessionId }: { tenantId: string; sessionId: string }) =>
      platformTenantsApi.revokeSession(tenantId, sessionId),
    onSuccess: () => {
      toast(t('mon.closed_ok'))
      qc.invalidateQueries({ queryKey: ['platform-monitoring'] })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !data) return <PageLoader />

  const { logins, sessions, errors } = data
  const readyUrl = `${window.location.origin}/api/v1/health/ready`

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t('mon.title')}
        action={
          <div className="flex items-center gap-3">
            <span className="text-xs text-tx-3">
              {t('mon.updated').replace('{time}', fmtTime(new Date(dataUpdatedAt).toISOString()))}
            </span>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
              {t('mon.refresh')}
            </Button>
          </div>
        }
      />
      <p className="-mt-2 text-[13px] text-tx-3">{t('mon.subtitle')}</p>

      <StatusStrip data={data} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div>
          <StatCard
            icon={ServerCrash}
            label={t('mon.errors_24h')}
            value={String(errors.last_24h)}
            unit={`/ ${errors.last_7d} ${t('mon.errors_7d').toLowerCase()}`}
          />
        </div>
        <div>
          <StatCard
            icon={ShieldAlert}
            label={t('mon.failing')}
            value={String(logins.failing_accounts)}
          />
          <p className="mt-1 px-1 text-xs text-tx-3">
            {t('mon.failing_hint').replace('{n}', String(logins.failed_attempts))}
          </p>
        </div>
        <div>
          <StatCard icon={Lock} label={t('mon.lockouts')} value={String(logins.lockouts_24h)} />
          <p className="mt-1 px-1 text-xs text-tx-3">{t('mon.lockouts_hint')}</p>
        </div>
        <div>
          <StatCard
            icon={Users}
            label={t('mon.sessions')}
            value={String(sessions.tenant + sessions.support + sessions.platform)}
          />
          <p className="mt-1 px-1 text-xs text-tx-3">
            {(['tenant', 'support', 'platform'] as const)
              .map((k) => `${t(`mon.sess.${k}`)} ${sessions[k]}`)
              .join(' · ')}
          </p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title={t('mon.support')} />
          {data.impersonations.length === 0 ? (
            <p className="px-5 py-6 text-sm text-tx-3">{t('mon.support_empty')}</p>
          ) : (
            <ul className="divide-y divide-line-soft">
              {data.impersonations.map((s) => (
                <li
                  key={s.session_id}
                  className="flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-tx">
                      <span className="font-medium">{s.admin_name ?? '—'}</span>{' '}
                      <button
                        className="text-tx-2 hover:text-accent hover:underline"
                        onClick={() => s.tenant_id && navigate(`/platform/clinics/${s.tenant_id}`)}
                      >
                        {t('mon.support_in').replace('{clinic}', s.clinic_name ?? '—')}
                      </button>
                    </p>
                    <p className="text-xs text-tx-3">
                      {fmtRelative(s.started_at)} ·{' '}
                      {t('mon.expires').replace('{time}', fmtTime(s.expires_at))}
                      {s.ip_address && ` · ${s.ip_address}`}
                    </p>
                  </div>
                  {s.tenant_id && (
                    <Button
                      variant="outline"
                      size="sm"
                      loading={closeSupport.isPending}
                      onClick={() =>
                        closeSupport.mutate({ tenantId: s.tenant_id!, sessionId: s.session_id })
                      }
                    >
                      {t('mon.close')}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title={t('mon.locked_now')} />
          {logins.locked.length === 0 ? (
            <p className="px-5 py-6 text-sm text-tx-3">{t('mon.locked_empty')}</p>
          ) : (
            <ul className="divide-y divide-line-soft">
              {logins.locked.map((l) => (
                <li
                  key={`${l.scope}:${l.clinic_slug}:${l.email}`}
                  className="flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-tx">{l.email}</p>
                    <p className="font-mono text-xs text-tx-3">
                      {l.scope === 'platform' ? t('mon.console') : l.clinic_slug}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <Badge tone="warn">
                      {t('mon.locked_until').replace('{time}', fmtTime(l.locked_until))}
                    </Badge>
                    <p className="mt-0.5 text-xs text-tx-3">
                      {t('mon.attempts').replace('{n}', String(l.failed_count))}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <ConsoleLogins logins={logins.console} />
        <ScheduledJobs jobs={data.jobs} />
      </div>

      <Card>
        <CardHeader title={t('mon.trend')} />
        <div className="p-5 pt-8">
          <TrendBars
            barClassName="bg-danger"
            points={errors.daily.map((d) => ({
              date: d.day,
              count: d.count,
              label: t('mon.trend_day')
                .replace('{date}', fmtDate(d.day, 'd MMM'))
                .replace('{n}', String(d.count)),
            }))}
          />
        </div>
      </Card>

      <Card>
        <CardHeader title={t('mon.errors_groups')} />
        {errors.groups.length === 0 ? (
          <p className="px-5 py-6 text-sm text-tx-3">{t('mon.errors_none')}</p>
        ) : (
          <Table>
            <thead>
              <Tr>
                <Th>{t('mon.col_route')}</Th>
                <Th>{t('mon.col_type')}</Th>
                <Th>{t('mon.col_location')}</Th>
                <Th className="text-right">{t('mon.col_count')}</Th>
                <Th>{t('mon.col_last')}</Th>
              </Tr>
            </thead>
            <tbody>
              {errors.groups.map((g) => (
                <Tr key={`${g.method} ${g.route} ${g.error_type} ${g.location}`}>
                  <Td className="font-mono text-xs text-tx-2">
                    <span className="text-tx-3">{g.method}</span> {g.route}
                  </Td>
                  <Td className="font-mono text-xs text-danger">{g.error_type}</Td>
                  <Td className="font-mono text-xs text-tx-3">
                    {g.location}
                    {data.runtime.commit && g.first_commit === data.runtime.commit && (
                      <Badge tone="danger" className="ml-2 font-sans">
                        {t('mon.new_in_deploy')}
                      </Badge>
                    )}
                    {data.runtime.commit && g.last_commit !== data.runtime.commit && (
                      <Badge tone="ok" className="ml-2 font-sans">
                        {t('mon.not_since_deploy')}
                      </Badge>
                    )}
                  </Td>
                  <Td className="text-right font-mono">{g.count}</Td>
                  <Td className="whitespace-nowrap text-sm text-tx-2">{fmtRelative(g.last_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <ErrorList retentionDays={errors.retention_days} />

      <PerformanceSection perf={data.performance} />

      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader title={t('mon.tables')} />
          <Table>
            <thead>
              <Tr>
                <Th>{t('mon.col_table')}</Th>
                <Th className="text-right">{t('mon.col_size')}</Th>
                <Th className="text-right">{t('mon.col_rows')}</Th>
              </Tr>
            </thead>
            <tbody>
              {data.largest_tables.map((tb) => (
                <Tr key={tb.name}>
                  <Td className="font-mono text-xs text-tx">{tb.name}</Td>
                  <Td className="text-right font-mono text-sm">{fmtBytes(tb.size_bytes)}</Td>
                  <Td className="text-right font-mono text-sm">{tb.rows.toLocaleString()}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card>
          <CardHeader title={t('mon.external')} />
          <div className="space-y-3 px-5 py-4">
            <p className="text-[13px] text-tx-2">{t('mon.external_desc')}</p>
            <div className="flex items-center gap-2 rounded-md border border-line bg-surface-2/60 px-3 py-2">
              <code className="flex-1 truncate font-mono text-xs text-tx">{readyUrl}</code>
              <Button
                variant="ghost"
                size="sm"
                aria-label={t('mon.copy')}
                onClick={() =>
                  navigator.clipboard?.writeText(readyUrl).then(() => toast(t('mon.copied')))
                }
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

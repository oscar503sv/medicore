import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Copy,
  Database,
  KeyRound,
  Lock,
  RefreshCw,
  Server,
  ServerCrash,
  ShieldAlert,
  Users,
} from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformTenantsApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Pager } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtBytes, fmtDateTime, fmtDuration, fmtRelative, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { SystemStatus } from '@/types'

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
  detail?: string
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
        {detail && <p className="truncate text-xs text-tx-3">{detail}</p>}
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
        detail={t('mon.latency').replace('{ms}', String(database.latency_ms))}
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
                  <Td className="font-mono text-xs text-tx-3">{g.location}</Td>
                  <Td className="text-right font-mono">{g.count}</Td>
                  <Td className="whitespace-nowrap text-sm text-tx-2">{fmtRelative(g.last_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <ErrorList retentionDays={errors.retention_days} />

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

import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, X } from 'lucide-react'
import { auditApi } from '@/api/audit'
import { AuditMetadata } from '@/components/audit/AuditMetadata'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { TONE_TEXT } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Select } from '@/components/ui/Input'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { actionLabel, auditDetail, categoryMeta, entityLabel, AUDIT_CATEGORIES } from '@/lib/audit'
import { cn } from '@/lib/cn'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'

export function AuditPage() {
  const t = useT()
  const [category, setCategory] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [offset, setOffset] = useState(0)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['audit', category, from, to, offset],
    queryFn: () =>
      auditApi.list({
        category: category || undefined,
        date_from: from || undefined,
        date_to: to || undefined,
        offset,
        limit: PAGE_SIZE,
      }),
  })

  // Reset to the first page whenever a filter changes.
  const onFilter = (apply: () => void) => {
    apply()
    setOffset(0)
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const hasFilters = !!(category || from || to)

  return (
    <div className="space-y-5 p-8">
      <PageHeader eyebrow={`${total} ${t('audit.events')}`} title={t('audit.title')} />

      <div className="flex flex-wrap items-center gap-4">
        <Select value={category} onChange={(e) => onFilter(() => setCategory(e.target.value))}>
          <option value="">{t('audit.cat_all')}</option>
          {AUDIT_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`audit.cat_${c}`)}
            </option>
          ))}
        </Select>
        <div className="flex items-center gap-2">
          <label className="text-[13px] text-tx-3">{t('audit.date_from')}</label>
          <input
            type="date"
            value={from}
            onChange={(e) => onFilter(() => setFrom(e.target.value))}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
          <label className="text-[13px] text-tx-3">{t('audit.date_to')}</label>
          <input
            type="date"
            value={to}
            onChange={(e) => onFilter(() => setTo(e.target.value))}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
        </div>
        {hasFilters && (
          <Button
            variant="outline"
            onClick={() =>
              onFilter(() => {
                setCategory('')
                setFrom('')
                setTo('')
              })
            }
          >
            <X className="h-4 w-4" />
            {t('audit.clear')}
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : items.length > 0 ? (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>{t('audit.col_date')}</Th>
                  <Th>{t('audit.col_user')}</Th>
                  <Th>{t('audit.col_action')}</Th>
                  <Th>{t('audit.col_detail')}</Th>
                  <Th>{t('audit.col_ip')}</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => {
                  const { icon: Icon, tone } = categoryMeta(e.action)
                  const expanded = expandedId === e.id
                  return (
                    <Fragment key={e.id}>
                      <Tr onClick={() => setExpandedId(expanded ? null : e.id)}>
                        <Td className="whitespace-nowrap text-[13px] text-tx-3">
                          {fmtDateTimeTz(e.timestamp)}
                        </Td>
                        <Td>
                          <div className="flex items-center gap-1.5">
                            <span className="font-medium text-tx">{e.actor_name ?? '—'}</span>
                            {e.metadata?.impersonated_by != null && (
                              <Badge tone="info">
                                <ShieldCheck className="h-3 w-3" />
                                {t('audit.support_badge')}
                              </Badge>
                            )}
                          </div>
                        </Td>
                        <Td className="text-[13px]">
                          <div className="flex items-center gap-2">
                            <Icon className={cn('h-3.5 w-3.5 shrink-0', TONE_TEXT[tone])} />
                            <span>{actionLabel(t, e.action)}</span>
                            <Badge tone="neutral">{entityLabel(t, e.entity_type)}</Badge>
                          </div>
                        </Td>
                        <Td className="text-[13px] text-tx-2">{auditDetail(e) || '—'}</Td>
                        <Td className="whitespace-nowrap font-mono text-[11px] text-tx-4">
                          {e.ip_address ?? '—'}
                        </Td>
                      </Tr>
                      {expanded && (
                        <tr>
                          <td colSpan={5} className="border-b border-line-soft bg-surface-2/40 px-4 py-3">
                            <AuditMetadata metadata={e.metadata} userAgent={e.user_agent} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </Table>
            <Pager offset={offset} limit={PAGE_SIZE} count={items.length} total={total} onChange={setOffset} />
          </>
        ) : (
          <EmptyState title={t('audit.title')} description={t('audit.empty')} />
        )}
      </Card>
    </div>
  )
}

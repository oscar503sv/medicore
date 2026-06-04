import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { platformAuditApi } from '@/api/platform'
import { AuditMetadata } from '@/components/audit/AuditMetadata'
import { PageHeader } from '@/components/PageHeader'
import { TONE_TEXT } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Select } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { actionLabel, auditDetail, categoryMeta, AUDIT_CATEGORIES } from '@/lib/audit'
import { cn } from '@/lib/cn'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { GlobalAuditEntry } from '@/types'
import { Pager } from '@/pages/AuditPage'

const PAGE_SIZE = 50

export function GlobalAuditPage() {
  const t = useT()
  const [category, setCategory] = useState('')
  const [offset, setOffset] = useState(0)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['platform-audit', category, offset],
    queryFn: () =>
      platformAuditApi.list({ category: category || undefined, offset, limit: PAGE_SIZE }),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  // Detail = metadata summary; for platform actions, prepend the affected clinic.
  const detailOf = (e: GlobalAuditEntry) => {
    const clinic = e.source_kind === 'platform' && e.clinic_name ? e.clinic_name : ''
    return [clinic, auditDetail(e)].filter(Boolean).join(' · ') || '—'
  }

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('platform.audit_title')} />

      <div className="flex flex-wrap items-center gap-4">
        <Select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value)
            setOffset(0)
          }}
        >
          <option value="">{t('audit.cat_all')}</option>
          {AUDIT_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`audit.cat_${c}`)}
            </option>
          ))}
        </Select>
        {category && (
          <Button
            variant="outline"
            onClick={() => {
              setCategory('')
              setOffset(0)
            }}
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
                <Tr>
                  <Th>{t('audit.col_date')}</Th>
                  <Th>{t('audit.col_source')}</Th>
                  <Th>{t('audit.col_user')}</Th>
                  <Th>{t('audit.col_action')}</Th>
                  <Th>{t('audit.col_detail')}</Th>
                  <Th>{t('audit.col_ip')}</Th>
                </Tr>
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
                        <Td className="text-[13px] text-tx">
                          {e.source_kind === 'platform' ? t('audit.source_platform') : e.clinic_name ?? '—'}
                        </Td>
                        <Td className="text-[13px] font-medium text-tx">{e.actor_name ?? '—'}</Td>
                        <Td className="text-[13px]">
                          <div className="flex items-center gap-2">
                            <Icon className={cn('h-3.5 w-3.5 shrink-0', TONE_TEXT[tone])} />
                            <span>{actionLabel(t, e.action)}</span>
                          </div>
                        </Td>
                        <Td className="text-[13px] text-tx-2">{detailOf(e)}</Td>
                        <Td className="whitespace-nowrap font-mono text-[11px] text-tx-4">
                          {e.ip_address ?? '—'}
                        </Td>
                      </Tr>
                      {expanded && (
                        <tr>
                          <td colSpan={6} className="border-b border-line-soft bg-surface-2/40 px-4 py-3">
                            <AuditMetadata metadata={e.metadata} />
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
          <EmptyState title={t('platform.audit_title')} description={t('audit.empty')} />
        )}
      </Card>
    </div>
  )
}

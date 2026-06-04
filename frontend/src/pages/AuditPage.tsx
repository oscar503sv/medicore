import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, ShieldCheck, X } from 'lucide-react'
import { auditApi } from '@/api/audit'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Select } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { actionLabel, auditDetail, AUDIT_CATEGORIES } from '@/lib/audit'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'

export function AuditPage() {
  const t = useT()
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['audit', category, from, to],
    queryFn: () =>
      auditApi.list({
        category: category || undefined,
        date_from: from || undefined,
        date_to: to || undefined,
        limit: 200,
      }),
  })

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (!term) return data ?? []
    return (data ?? []).filter(
      (e) =>
        actionLabel(t, e.action).toLowerCase().includes(term) ||
        (e.actor_name ?? '').toLowerCase().includes(term) ||
        auditDetail(t, e).toLowerCase().includes(term),
    )
  }, [data, q, t])

  return (
    <div className="space-y-5 p-8">
      <PageHeader eyebrow={`${filtered.length} ${t('audit.events')}`} title={t('audit.title')} />

      <div className="flex flex-wrap items-center gap-4">
        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('audit.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        <Select value={category} onChange={(e) => setCategory(e.target.value)}>
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
            onChange={(e) => setFrom(e.target.value)}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
          <label className="text-[13px] text-tx-3">{t('audit.date_to')}</label>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
        </div>
        {(q || category || from || to) && (
          <Button
            variant="outline"
            onClick={() => {
              setQ('')
              setCategory('')
              setFrom('')
              setTo('')
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
        ) : filtered.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>{t('audit.col_date')}</Th>
                <Th>{t('audit.col_user')}</Th>
                <Th>{t('audit.col_action')}</Th>
                <Th>{t('audit.col_detail')}</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <Tr key={e.id}>
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
                  <Td className="text-[13px]">{actionLabel(t, e.action)}</Td>
                  <Td className="text-[13px] text-tx-2">{auditDetail(t, e)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState title={t('audit.title')} description={t('audit.empty')} />
        )}
      </Card>
    </div>
  )
}

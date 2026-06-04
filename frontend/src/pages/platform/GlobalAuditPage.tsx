import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { platformAuditApi, platformTenantsApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Select } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { actionLabel, auditDetail, AUDIT_CATEGORIES } from '@/lib/audit'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { Pager } from '@/pages/AuditPage'

const PAGE_SIZE = 50

export function GlobalAuditPage() {
  const t = useT()
  const [category, setCategory] = useState('')
  const [offset, setOffset] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['platform-audit', category, offset],
    queryFn: () =>
      platformAuditApi.list({
        category: category || undefined,
        offset,
        limit: PAGE_SIZE,
      }),
  })

  // Resolve clinic names for the tenant_id column (small, cached list; endpoint caps at 200).
  const { data: tenants } = useQuery({
    queryKey: ['platform-tenants', 'audit-names'],
    queryFn: () => platformTenantsApi.list({ limit: 200 }),
  })
  const tenantName = useMemo(() => {
    const map = new Map<string, string>()
    for (const c of tenants?.items ?? []) map.set(c.id, c.legal_name)
    return map
  }, [tenants])

  const items = data?.items ?? []
  const total = data?.total ?? 0

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
                  <Th>{t('audit.col_clinic')}</Th>
                  <Th>{t('audit.col_action')}</Th>
                  <Th>{t('audit.col_detail')}</Th>
                </Tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <Tr key={e.id}>
                    <Td className="whitespace-nowrap text-[13px] text-tx-3">
                      {fmtDateTimeTz(e.timestamp)}
                    </Td>
                    <Td className="text-[13px] text-tx">
                      {(e.tenant_id && tenantName.get(e.tenant_id)) || '—'}
                    </Td>
                    <Td className="text-[13px]">{actionLabel(t, e.action)}</Td>
                    <Td className="text-[13px] text-tx-2">{auditDetail(t, e)}</Td>
                  </Tr>
                ))}
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

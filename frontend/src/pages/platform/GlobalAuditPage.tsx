import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { platformAuditApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { useT } from '@/lib/i18n'

export function GlobalAuditPage() {
  const t = useT()
  const [action, setAction] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['platform-audit', action],
    queryFn: () => platformAuditApi.list({ action: action || undefined, limit: 200 }),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('platform.audit_title')} />

      <div className="max-w-xs">
        <Input
          label={t('platform.audit_filter_action')}
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="auth.login"
        />
      </div>

      <Card>
        {isLoading || !data ? (
          <PageLoader />
        ) : (
          <Table>
            <thead>
              <Tr>
                <Th>{t('platform.audit_time')}</Th>
                <Th>{t('platform.audit_action')}</Th>
                <Th>{t('platform.audit_entity')}</Th>
                <Th>{t('platform.col_name')}</Th>
              </Tr>
            </thead>
            <tbody>
              {data.map((e) => (
                <Tr key={e.id}>
                  <Td className="whitespace-nowrap text-[13px] text-tx-3">
                    {new Date(e.timestamp).toLocaleString()}
                  </Td>
                  <Td className="font-mono text-[13px]">{e.action}</Td>
                  <Td className="text-[13px]">
                    {e.entity_type} · <span className="text-tx-4">{e.entity_id.slice(0, 8)}</span>
                  </Td>
                  <Td className="font-mono text-[11px] text-tx-4">{e.tenant_id.slice(0, 8)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}

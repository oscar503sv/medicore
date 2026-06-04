import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Activity, Building2, CalendarCheck, Users } from 'lucide-react'
import { platformTenantsApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { useT } from '@/lib/i18n'
import type { TenantStatus } from '@/types'

const STATUS_TONE: Record<TenantStatus, 'ok' | 'danger' | 'neutral'> = {
  active: 'ok',
  suspended: 'danger',
  archived: 'neutral',
}

export function GlobalStatsPage() {
  const t = useT()
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const { data, isLoading } = useQuery({
    queryKey: ['platform-stats'],
    queryFn: platformTenantsApi.stats,
  })

  if (isLoading || !data) return <PageLoader />

  const paged = data.by_clinic.slice(offset, offset + PAGE_SIZE)

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('platform.stats_title')} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={Building2} label={t('platform.total_clinics')} value={String(data.total_clinics)} />
        <StatCard icon={Users} label={t('platform.total_users')} value={String(data.total_users)} />
        <StatCard icon={Users} label={t('platform.total_patients')} value={String(data.total_patients)} />
        <StatCard icon={CalendarCheck} label={t('platform.total_appointments')} value={String(data.total_appointments)} />
      </div>

      <Card>
        <Table>
          <thead>
            <Tr>
              <Th>{t('platform.col_name')}</Th>
              <Th>{t('platform.col_status')}</Th>
              <Th>{t('platform.total_patients')}</Th>
              <Th>{t('platform.total_users')}</Th>
              <Th>{t('platform.total_appointments')}</Th>
              <Th>{t('platform.col_consultations')}</Th>
            </Tr>
          </thead>
          <tbody>
            {paged.map((c) => (
              <Tr key={c.tenant_id} onClick={() => navigate(`/platform/clinics/${c.tenant_id}`)}>
                <Td className="font-medium text-tx">
                  <Activity className="mr-2 inline h-3.5 w-3.5 text-tx-4" />
                  {c.legal_name}
                </Td>
                <Td>
                  <Badge tone={STATUS_TONE[c.status]}>{t(`platform.status_${c.status}`)}</Badge>
                </Td>
                <Td>{c.patients}</Td>
                <Td>{c.users}</Td>
                <Td>{c.appointments}</Td>
                <Td>{c.consultations}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        {data.by_clinic.length > PAGE_SIZE && (
          <Pager offset={offset} limit={PAGE_SIZE} count={paged.length} total={data.by_clinic.length} onChange={setOffset} />
        )}
      </Card>
    </div>
  )
}

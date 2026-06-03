import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search, UserCheck, Users, UserX } from 'lucide-react'
import { patientsApi } from '@/api/patients'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { NewPatientModal } from '@/components/patients/NewPatientModal'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtDate, fmtDateTime } from '@/lib/format'
import { useT } from '@/lib/i18n'

export function PatientsPage() {
  const t = useT()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [modalOpen, setModalOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['patients', { q, filter }],
    queryFn: () =>
      patientsApi.list({
        q: q || undefined,
        status: filter === 'all' ? undefined : filter,
      }),
  })

  // Accurate counts for the stat cards (independent of the table's current filter).
  const { data: activeTotal } = useQuery({
    queryKey: ['patients-count', 'active'],
    queryFn: async () => (await patientsApi.list({ status: 'active', limit: 1 })).total,
  })
  const { data: inactiveTotal } = useQuery({
    queryKey: ['patients-count', 'inactive'],
    queryFn: async () => (await patientsApi.list({ status: 'inactive', limit: 1 })).total,
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={`${data?.total ?? 0} registrados`}
        title={t('patients.title')}
        action={
          <Button onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            {t('patients.new')}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard
          icon={Users}
          label={t('patients.stat_total')}
          value={String((activeTotal ?? 0) + (inactiveTotal ?? 0))}
        />
        <StatCard icon={UserCheck} label={t('patients.active')} value={String(activeTotal ?? 0)} />
        <StatCard icon={UserX} label={t('patients.inactive')} value={String(inactiveTotal ?? 0)} />
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('patients.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        <Segmented
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: t('app.all') },
            { value: 'active', label: t('patients.active') },
            { value: 'inactive', label: t('patients.inactive') },
          ]}
        />
      </div>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : data && data.items.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>{t('patients.col_patient')}</Th>
                <Th>{t('patients.col_age')}</Th>
                <Th>{t('patients.col_tags')}</Th>
                <Th>{t('patients.col_last')}</Th>
                <Th>{t('patients.col_next')}</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <Tr key={p.id} onClick={() => navigate(`/patients/${p.id}`)}>
                  <Td>
                    <div className="flex items-center gap-3">
                      <Avatar name={`${p.first_name} ${p.last_name}`} size="sm" />
                      <div>
                        <p className="font-medium text-tx">
                          {p.first_name} {p.last_name}
                        </p>
                        <p className="font-mono text-xs text-tx-3">{p.code}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    {p.age} · {p.sex === 'male' ? 'M' : p.sex === 'female' ? 'F' : 'O'}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {p.tags.slice(0, 2).map((tag) => (
                        <Badge key={tag} tone="accent">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </Td>
                  <Td>{fmtDate(p.updated_at)}</Td>
                  <Td>{p.next_visit ? fmtDateTime(p.next_visit) : '—'}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState title="Sin pacientes" description="Registra el primer paciente para empezar." />
        )}
      </Card>

      <NewPatientModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { recordsApi } from '@/api/records'
import { RecordDrawer } from '@/components/records/RecordDrawer'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'

export function RecordsPage() {
  const t = useT()
  const [openId, setOpenId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['records', 'all'],
    queryFn: () => recordsApi.list(),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader eyebrow={`${data?.length ?? 0} registros`} title={t('records.title')} />

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : data && data.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>Código</Th>
                <Th>Motivo</Th>
                <Th>Tipo</Th>
                <Th>Encuentro</Th>
                <Th>Estado</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <Tr key={r.id} onClick={() => setOpenId(r.id)}>
                  <Td>
                    <span className="font-mono text-[13px] text-tx">{r.code}</span>
                  </Td>
                  <Td className="font-medium text-tx">{r.chief_complaint}</Td>
                  <Td>{r.type}</Td>
                  <Td>{fmtDate(r.encounter_at)}</Td>
                  <Td>
                    <Badge tone={r.status === 'amended' ? 'info' : 'ok'}>
                      {t(`records.${r.status === 'amended' ? 'amended' : 'signed'}`)}
                    </Badge>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState title="Sin historiales" description="Aún no hay registros firmados." />
        )}
      </Card>

      <RecordDrawer recordId={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}

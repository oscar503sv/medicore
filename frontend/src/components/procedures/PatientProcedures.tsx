import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Plus } from 'lucide-react'
import { proceduresApi } from '@/api/procedures'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtDate, fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { STATUS_TONE, usePerformer } from '@/lib/procedures'
import { NewProcedureModal, type PickedPatient } from './NewProcedureModal'
import { ProcedureCell } from './ProcedureCell'

/** Patient tab: every procedure (ordered, done, cancelled), newest first. */
export function PatientProcedures({
  patient,
  active,
}: {
  patient: PickedPatient
  /** Archived patients can't get new procedures. */
  active: boolean
}) {
  const t = useT()
  const navigate = useNavigate()
  const { canPerform } = usePerformer()
  const [creating, setCreating] = useState(false)
  const { data } = useQuery({
    queryKey: ['procedures-patient', patient.id],
    queryFn: () => proceduresApi.patient(patient.id),
  })

  if (!data) return <PageLoader />
  return (
    <div className="space-y-4">
      {canPerform && active && (
        <div className="flex justify-end">
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            {t('prc.new')}
          </Button>
        </div>
      )}
      <Card>
        {data.length === 0 ? (
          <EmptyState icon={ClipboardList} title={t('prc.empty_patient')} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t('prc.col_procedure')}</Th>
                <Th>{t('prc.col_status')}</Th>
                <Th>{t('prc.col_since')}</Th>
                <Th>{t('prc.col_by')}</Th>
                <Th>{t('prc.col_follow_up')}</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <Tr key={p.id} onClick={() => navigate(`/procedures/${p.id}`)}>
                  <Td>
                    <ProcedureCell p={p} />
                  </Td>
                  <Td>
                    <Badge tone={STATUS_TONE[p.status]}>{t(`prc.status.${p.status}`)}</Badge>
                  </Td>
                  <Td className="whitespace-nowrap text-[13px] text-tx-2">
                    {fmtDateTimeTz(p.performed_at ?? p.created_at)}
                  </Td>
                  <Td className="text-[13px] text-tx-2">
                    {p.performed_by_name ?? p.ordered_by_name ?? '—'}
                  </Td>
                  <Td className="whitespace-nowrap text-[13px] text-tx-2">
                    {p.follow_up_on ? fmtDate(p.follow_up_on) : '—'}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <NewProcedureModal open={creating} onClose={() => setCreating(false)} patient={patient} />
    </div>
  )
}

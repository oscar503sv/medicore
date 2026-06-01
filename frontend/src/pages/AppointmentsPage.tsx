import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Stethoscope } from 'lucide-react'
import { format } from 'date-fns'
import { appointmentsApi } from '@/api/appointments'
import { consultationsApi } from '@/api/consultations'
import { errorMessage } from '@/api/client'
import { NewAppointmentModal } from '@/components/appointments/NewAppointmentModal'
import { PageHeader } from '@/components/PageHeader'
import { Badge, statusTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

export function AppointmentsPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const canConsult = useAuthStore((s) => s.hasRole('doctor', 'admin'))
  const [date, setDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [modalOpen, setModalOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['appointments', 'day', date],
    queryFn: () => appointmentsApi.listForDay(date),
  })

  const startConsult = useMutation({
    mutationFn: (appointmentId: string) => consultationsApi.start(appointmentId),
    onSuccess: (consultation) => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      navigate(`/consultation/${consultation.id}`)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t('appt.title')}
        action={
          <Button onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            {t('appt.new')}
          </Button>
        }
      />

      <div className="flex items-center gap-3">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
        />
      </div>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : data && data.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>{t('appt.col_time')}</Th>
                <Th>{t('appt.col_reason')}</Th>
                <Th>{t('appt.col_type')}</Th>
                <Th>{t('appt.col_room')}</Th>
                <Th>{t('appt.col_status')}</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <Tr key={a.id}>
                  <Td>
                    <span className="font-mono text-tx">{fmtTime(a.scheduled_start)}</span>
                    <span className="text-tx-4"> · {a.duration_minutes}m</span>
                  </Td>
                  <Td>
                    <p className="font-medium text-tx">{a.reason}</p>
                    <p className="font-mono text-xs text-tx-3">{a.code}</p>
                  </Td>
                  <Td>{a.type}</Td>
                  <Td>{a.room ?? '—'}</Td>
                  <Td>
                    <Badge tone={statusTone(a.status)}>{t(`status.${a.status}`)}</Badge>
                  </Td>
                  <Td className="text-right">
                    {canConsult && (a.status === 'scheduled' || a.status === 'confirmed') && (
                      <Button
                        size="sm"
                        variant="outline"
                        loading={startConsult.isPending}
                        onClick={() => startConsult.mutate(a.id)}
                      >
                        <Stethoscope className="h-3.5 w-3.5" />
                        {t('appt.start_consult')}
                      </Button>
                    )}
                    {a.status === 'in_progress' && canConsult && (
                      <Button size="sm" variant="subtle" onClick={() => startConsult.mutate(a.id)}>
                        Continuar
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState title="Sin citas" description="No hay citas para esta fecha." />
        )}
      </Card>

      <NewAppointmentModal open={modalOpen} onClose={() => setModalOpen(false)} date={date} />
    </div>
  )
}

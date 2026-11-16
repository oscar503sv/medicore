import { CalendarCheck, Syringe } from 'lucide-react'
import type { WorklistAppointment } from '@/api/vaccinations'
import { WalkInBadge } from '@/components/appointments/WalkInBadge'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { statusTone } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { VisitTarget } from './useVaccinationVisit'

/** Today's open vaccination appointments, with the entry point to record their doses. */
export function TodayAppointments({
  rows,
  canRecord,
  onRecord,
}: {
  rows: WorklistAppointment[]
  canRecord: boolean
  onRecord: (target: VisitTarget) => void
}) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={CalendarCheck} title={t('vax.empty_appts')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('appt.col_time')}</Th>
          <Th>{t('vax.col_patient')}</Th>
          <Th>{t('appt.attends')}</Th>
          <Th>{t('appt.col_status')}</Th>
          <Th />
        </tr>
      </thead>
      <tbody>
        {rows.map(({ appointment: a, patient, attendant_name }) => (
          <Tr key={a.id}>
            <Td className="whitespace-nowrap font-mono text-tx">
              {fmtTime(a.scheduled_start)}
              {a.is_walk_in && (
                <span className="ml-2 align-middle font-sans">
                  <WalkInBadge />
                </span>
              )}
            </Td>
            <Td>
              <div className="flex items-center gap-3">
                <Avatar name={patient.name} size="sm" />
                <div className="min-w-0">
                  <p className="font-medium text-tx">{patient.name}</p>
                  <p className="font-mono text-xs text-tx-3">{a.code}</p>
                </div>
              </div>
            </Td>
            <Td className="text-tx-2">{attendant_name ?? '—'}</Td>
            <Td>
              <Badge tone={statusTone(a.status)}>{t(`status.${a.status}`)}</Badge>
            </Td>
            <Td className="text-right">
              {canRecord && (
                <Button
                  size="sm"
                  onClick={() =>
                    onRecord({
                      appointmentId: a.id,
                      patientId: patient.id,
                      patientName: patient.name,
                    })
                  }
                >
                  <Syringe className="h-3.5 w-3.5" />
                  {t('vax.visit_cta')}
                </Button>
              )}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

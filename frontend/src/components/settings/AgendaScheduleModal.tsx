import { useMemo } from 'react'
import type { ServiceAgenda } from '@/api/serviceAgendas'
import { agendaAvailability } from '@/api/availability'
import { AvailabilityEditor } from '@/components/availability/AvailabilityEditor'
import { Modal } from '@/components/ui/Modal'
import { useT } from '@/lib/i18n'

/** The agenda's own weekly hours, exceptions and booking rules (same editor as a doctor's). */
export function AgendaScheduleModal({
  agenda,
  onClose,
}: {
  agenda: ServiceAgenda | null
  onClose: () => void
}) {
  const t = useT()
  const scope = useMemo(() => (agenda ? agendaAvailability(agenda.id) : null), [agenda])
  return (
    <Modal
      open={agenda !== null}
      onClose={onClose}
      title={agenda ? t('agenda.schedule_title').replace('{name}', agenda.name) : ''}
      width="max-w-4xl"
    >
      <div className="max-h-[75vh] overflow-y-auto p-5">
        {agenda && scope && (
          <AvailabilityEditor key={agenda.id} scope={scope} scopeKey={`agenda-${agenda.id}`} />
        )}
      </div>
    </Modal>
  )
}

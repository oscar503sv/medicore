import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import {
  serviceAgendasApi,
  type CreateServiceAgendaPayload,
  type UpdateServiceAgendaPayload,
} from '@/api/serviceAgendas'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'

/** The clinic's service agendas (archived ones included) and the actions to manage them. */
export function useServiceAgendas() {
  const t = useT()
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['service-agendas'],
    queryFn: () => serviceAgendasApi.list(false),
  })

  // Booking forms read the active agendas from booking-options.
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['service-agendas'] })
    qc.invalidateQueries({ queryKey: ['booking-options'] })
  }
  const onError = (err: unknown) => toast(errorMessage(err), 'danger')

  const create = useMutation({
    mutationFn: (payload: CreateServiceAgendaPayload) => serviceAgendasApi.create(payload),
    onSuccess: () => {
      refresh()
      toast(t('agenda.created_ok'))
    },
    onError,
  })
  const update = useMutation({
    mutationFn: (v: { id: string; changes: UpdateServiceAgendaPayload }) =>
      serviceAgendasApi.update(v.id, v.changes),
    onSuccess: () => {
      refresh()
      toast(t('agenda.updated_ok'))
    },
    onError,
  })
  const setActive = useMutation({
    mutationFn: (v: { id: string; active: boolean }) => serviceAgendasApi.setActive(v.id, v.active),
    onSuccess: (agenda) => {
      refresh()
      toast(t(agenda.active ? 'agenda.activated_ok' : 'agenda.archived_ok'))
    },
    onError,
  })

  return { list, create, update, setActive }
}

import { useState } from 'react'
import { CalendarClock, MapPin, Pencil, Plus, Syringe } from 'lucide-react'
import { errorMessage } from '@/api/client'
import type { ServiceAgenda } from '@/api/serviceAgendas'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { useT } from '@/lib/i18n'
import type { Location } from '@/types'
import { AgendaFormModal } from './AgendaFormModal'
import { AgendaScheduleModal } from './AgendaScheduleModal'
import { useServiceAgendas } from './useServiceAgendas'

/** Agendas a clinic books without a doctor (e.g. the vaccination room), with their own hours. */
export function ServiceAgendasSection({ locations }: { locations: Location[] }) {
  const t = useT()
  const { list, create, update, setActive } = useServiceAgendas()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<ServiceAgenda | null>(null)
  const [scheduling, setScheduling] = useState<ServiceAgenda | null>(null)

  const agendas = list.data ?? []
  const locationName = (id: string | null) => locations.find((l) => l.id === id)?.name
  const openCreate = () => {
    setEditing(null)
    create.reset()
    setFormOpen(true)
  }
  const openEdit = (agenda: ServiceAgenda) => {
    setEditing(agenda)
    update.reset()
    setFormOpen(true)
  }
  const mutation = editing ? update : create

  return (
    <Card>
      <CardHeader
        title={t('agenda.section')}
        action={
          <Button size="sm" variant="outline" onClick={openCreate}>
            <Plus className="h-3.5 w-3.5" />
            {t('agenda.add')}
          </Button>
        }
      />
      <p className="px-5 pt-4 text-[13px] text-tx-3">{t('agenda.section_desc')}</p>

      {list.isLoading ? (
        <PageLoader />
      ) : list.isError ? (
        <p role="alert" className="px-5 py-8 text-center text-sm text-danger">
          {errorMessage(list.error)}
        </p>
      ) : agendas.length === 0 ? (
        <EmptyState
          icon={Syringe}
          title={t('agenda.empty_title')}
          description={t('agenda.empty_desc')}
        />
      ) : (
        <ul className="mt-2 divide-y divide-line-soft">
          {agendas.map((a) => (
            <li
              key={a.id}
              className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5"
            >
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium text-tx">
                  {a.name}
                  <Badge tone={a.active ? 'ok' : 'neutral'}>
                    {t(a.active ? 'agenda.active' : 'agenda.archived')}
                  </Badge>
                </p>
                <p className="flex items-center gap-1.5 text-xs text-tx-3">
                  <MapPin className="h-3 w-3" />
                  {locationName(a.location_id) ?? t('agenda.location_none')}
                  {' · '}
                  {a.slot_minutes
                    ? t('agenda.slot').replace('{n}', String(a.slot_minutes))
                    : t('agenda.no_schedule')}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => setScheduling(a)}>
                  <CalendarClock className="h-3.5 w-3.5" />
                  {t('agenda.schedule')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => openEdit(a)}>
                  <Pencil className="h-3.5 w-3.5" />
                  {t('agenda.rename')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={setActive.isPending && setActive.variables?.id === a.id}
                  onClick={() => setActive.mutate({ id: a.id, active: !a.active })}
                >
                  {t(a.active ? 'agenda.archive' : 'agenda.reactivate')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <AgendaFormModal
        open={formOpen}
        agenda={editing}
        locations={locations}
        isSaving={mutation.isPending}
        error={mutation.isError ? errorMessage(mutation.error) : null}
        onClose={() => setFormOpen(false)}
        onSubmit={(values) => {
          const done = { onSuccess: () => setFormOpen(false) }
          if (editing) update.mutate({ id: editing.id, changes: values }, done)
          else create.mutate({ ...values, kind: 'vaccination' }, done)
        }}
      />
      <AgendaScheduleModal agenda={scheduling} onClose={() => setScheduling(null)} />
    </Card>
  )
}

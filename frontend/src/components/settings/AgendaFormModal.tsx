import { useEffect, useId, useState } from 'react'
import type { ServiceAgenda } from '@/api/serviceAgendas'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { useT } from '@/lib/i18n'
import type { Location } from '@/types'

const NAME_MAX = 80

/** Create (agenda null) or edit a service agenda: its name and, optionally, its location. */
export function AgendaFormModal({
  open,
  agenda,
  locations,
  isSaving,
  error,
  onSubmit,
  onClose,
}: {
  open: boolean
  agenda: ServiceAgenda | null
  locations: Location[]
  isSaving: boolean
  /** Server-side error of the last attempt (e.g. a name already taken). */
  error: string | null
  onSubmit: (values: { name: string; location_id: string | null }) => void
  onClose: () => void
}) {
  const t = useT()
  const errorId = useId()
  const [name, setName] = useState('')
  const [locationId, setLocationId] = useState('')

  useEffect(() => {
    if (!open) return
    setName(agenda?.name ?? '')
    setLocationId(agenda?.location_id ?? '')
  }, [open, agenda])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t(agenda ? 'agenda.edit_title' : 'agenda.new_title')}
      width="max-w-md"
    >
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit({ name: name.trim(), location_id: locationId || null })
        }}
      >
        <Input
          label={t('agenda.name')}
          value={name}
          maxLength={NAME_MAX}
          placeholder={t('agenda.name_ph')}
          required
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => setName(e.target.value)}
        />
        <Select
          label={t('agenda.location')}
          value={locationId}
          hint={t('agenda.location_hint')}
          onChange={(e) => setLocationId(e.target.value)}
        >
          <option value="">{t('agenda.location_none')}</option>
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </Select>
        {error && (
          <p id={errorId} role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={isSaving} disabled={!name.trim()}>
            {t('app.save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

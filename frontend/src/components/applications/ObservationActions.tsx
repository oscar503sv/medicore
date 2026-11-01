import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, Timer } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { applicationsApi, type ApplicationOrder, type ApplicationRecord } from '@/api/applications'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useMinutesLeft } from '@/lib/applications'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'

/** "Quedan 12 min" while the window runs, "Observación cumplida" once it is over. */
export function ObservationTimer({ record }: { record: ApplicationRecord }) {
  const t = useT()
  const left = useMinutesLeft(record.observe_until)
  if (left === null) return null
  const done = left <= 0
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] tabular-nums',
        done ? 'text-ok' : 'text-warn',
      )}
    >
      {done ? <Check className="h-3.5 w-3.5" /> : <Timer className="h-3.5 w-3.5" />}
      {done ? t('apl.obs_done') : t('apl.obs_left').replace('{m}', String(left))}
    </span>
  )
}

/** Close an observation: "Sin reacción" in one click, or describe an adverse reaction. */
export function ObservationActions({
  record,
  order,
}: {
  record: ApplicationRecord
  order: ApplicationOrder
}) {
  const t = useT()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState('')
  useEffect(() => {
    if (open) setNotes('')
  }, [open])

  const close = useMutation({
    mutationFn: (reaction: boolean) =>
      applicationsApi.closeObservation(record.id, reaction, reaction ? notes.trim() : null),
    onSuccess: (_, reaction) => {
      qc.invalidateQueries({ queryKey: ['applications-worklist'] })
      qc.invalidateQueries({ queryKey: ['applications-patient', order.patient_id] })
      toast(t(reaction ? 'apl.reaction_ok' : 'apl.closed_ok'))
      setOpen(false)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
      <Button
        size="sm"
        variant="outline"
        loading={close.isPending && !open}
        onClick={() => close.mutate(false)}
      >
        <Check className="h-3.5 w-3.5" />
        {t('apl.no_reaction')}
      </Button>
      <Button size="sm" variant="ghost" className="text-danger" onClick={() => setOpen(true)}>
        <AlertTriangle className="h-3.5 w-3.5" />
        {t('apl.reaction')}
      </Button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={t('apl.reaction_title')}
        width="max-w-md"
      >
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            close.mutate(true)
          }}
        >
          <p className="text-sm text-tx-2">
            {order.drug} {order.dose}
          </p>
          <Textarea
            label={t('apl.reaction_notes')}
            rows={3}
            value={notes}
            placeholder={t('apl.reaction_notes_ph')}
            onChange={(e) => setNotes(e.target.value)}
            autoFocus
            required
          />
          <p className="text-xs text-tx-3">
            {t(order.source === 'internal' ? 'apl.reaction_hint' : 'apl.reaction_hint_external')}
          </p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {t('app.cancel')}
            </Button>
            <Button
              type="submit"
              variant="danger"
              loading={close.isPending}
              disabled={!notes.trim()}
            >
              {t('apl.reaction_title')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

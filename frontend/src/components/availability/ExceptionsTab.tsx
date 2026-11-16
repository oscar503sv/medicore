import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarOff, Plus, Trash2 } from 'lucide-react'
import type { AvailabilityScope } from '@/api/availability'
import { errorMessage } from '@/api/client'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { AvailabilityException, TimeRange } from '@/types'
import { BlockEditor } from './WeeklyEditor'

export function ExceptionsTab({
  exceptions,
  scope,
}: {
  exceptions: AvailabilityException[]
  scope: AvailabilityScope
}) {
  const t = useT()
  const qc = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)

  const remove = useMutation({
    mutationFn: (id: string) => scope.removeException(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability'] })
      toast(t('avail.exception_removed'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const sorted = [...exceptions].sort((a, b) => a.date.localeCompare(b.date))

  return (
    <Card>
      {exceptions.length === 0 ? (
        <EmptyState
          icon={CalendarOff}
          title={t('avail.no_exceptions')}
          description={t('avail.no_exceptions_desc')}
          action={
            <Button onClick={() => setModalOpen(true)}>
              <Plus className="h-4 w-4" />
              {t('avail.add_exception')}
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex justify-end p-3">
            <Button size="sm" onClick={() => setModalOpen(true)}>
              <Plus className="h-4 w-4" />
              {t('avail.add_exception')}
            </Button>
          </div>
          <Table>
            <thead>
              <tr>
                <Th>{t('avail.col_date')}</Th>
                <Th>{t('avail.col_day')}</Th>
                <Th>{t('avail.col_type')}</Th>
                <Th>{t('avail.col_reason')}</Th>
                <Th>{t('avail.col_schedule')}</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {sorted.map((ex) => (
                <Tr key={ex.id}>
                  <Td className="font-mono text-tx">{ex.date}</Td>
                  <Td className="capitalize text-tx-3">{fmtDate(ex.date, 'EEEE')}</Td>
                  <Td>
                    <Badge tone={ex.kind === 'off' ? 'warn' : 'ok'}>
                      {ex.kind === 'off' ? t('avail.kind_off') : t('avail.kind_extra')}
                    </Badge>
                  </Td>
                  <Td className="text-tx">{ex.reason || '—'}</Td>
                  <Td className="font-mono text-tx-3">
                    {ex.kind === 'off'
                      ? t('avail.all_day')
                      : ex.blocks.map((b) => `${b.start}–${b.end}`).join(', ')}
                  </Td>
                  <Td className="text-right">
                    <button
                      type="button"
                      onClick={() => remove.mutate(ex.id)}
                      className="text-tx-4 hover:text-danger"
                      title={t('app.cancel')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
      <ExceptionModal open={modalOpen} onClose={() => setModalOpen(false)} scope={scope} />
    </Card>
  )
}

function ExceptionModal({
  open,
  onClose,
  scope,
}: {
  open: boolean
  onClose: () => void
  scope: AvailabilityScope
}) {
  const t = useT()
  const qc = useQueryClient()
  const today = clinicToday()
  const [date, setDate] = useState(today)
  const [kind, setKind] = useState<'off' | 'extra'>('off')
  const [reason, setReason] = useState('')
  const [blocks, setBlocks] = useState<TimeRange[]>([{ start: '14:00', end: '18:00' }])

  function reset() {
    setDate(today)
    setKind('off')
    setReason('')
    setBlocks([{ start: '14:00', end: '18:00' }])
  }

  const add = useMutation({
    mutationFn: () =>
      scope.addException({
        date,
        kind,
        reason,
        blocks: kind === 'extra' ? blocks : [],
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability'] })
      toast(t('avail.exception_added'))
      reset()
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const valid = reason.trim() && (kind === 'off' || blocks.length > 0)

  return (
    <Modal open={open} onClose={onClose} title={t('avail.add_exception')} width="max-w-md">
      <div className="space-y-4 p-5">
        <Input
          label={t('avail.col_date')}
          type="date"
          min={today}
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="font-mono"
        />
        <div>
          <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
            {t('avail.col_type')}
          </span>
          <div className="flex gap-2">
            {(['off', 'extra'] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={cn(
                  'flex-1 rounded-lg border px-3 py-2 text-[13px] font-medium transition-colors',
                  kind === k
                    ? 'border-accent bg-[var(--accent-10)] text-accent'
                    : 'border-line text-tx-3 hover:text-tx',
                )}
              >
                {k === 'off' ? t('avail.kind_off') : t('avail.kind_extra')}
              </button>
            ))}
          </div>
        </div>
        <Input
          label={t('avail.col_reason')}
          placeholder={t('avail.reason_ph')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        {kind === 'extra' && (
          <div>
            <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
              {t('avail.col_schedule')}
            </span>
            <BlockEditor blocks={blocks} onChange={setBlocks} />
          </div>
        )}
      </div>
      <div className="flex justify-between border-t border-line px-5 py-4">
        <Button variant="outline" onClick={onClose}>
          {t('app.cancel')}
        </Button>
        <Button disabled={!valid} loading={add.isPending} onClick={() => add.mutate()}>
          {t('avail.add_exception')}
        </Button>
      </div>
    </Modal>
  )
}

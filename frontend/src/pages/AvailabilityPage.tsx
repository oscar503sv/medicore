import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO, startOfWeek } from 'date-fns'
import { CalendarOff, Plus, Trash2 } from 'lucide-react'
import { availabilityApi } from '@/api/availability'
import { errorMessage } from '@/api/client'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { AvailabilityException, BookingRules, TimeRange, WeeklyDay } from '@/types'

const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
type Tab = 'weekly' | 'exceptions' | 'rules' | 'preview'

// Fixed grid of selectable times (07:00–22:00 every 15 min) — selects, not free text,
// so a block can never hold an invalid value (SPEC PARTE E.1).
const TIME_OPTIONS: string[] = (() => {
  const out: string[] = []
  for (let m = 7 * 60; m <= 22 * 60; m += 15) {
    out.push(`${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`)
  }
  return out
})()

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function blocksMinutes(blocks: TimeRange[]): number {
  return blocks.reduce((sum, b) => sum + Math.max(0, toMinutes(b.end) - toMinutes(b.start)), 0)
}

export function AvailabilityPage() {
  const t = useT()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('weekly')

  const { data, isLoading } = useQuery({
    queryKey: ['availability', 'me'],
    queryFn: () => availabilityApi.getMine(),
  })

  if (isLoading || !data) return <PageLoader />

  const activeDays = data.weekly.filter((d) => d.enabled).length
  const weekMinutes = data.weekly.reduce((sum, d) => sum + (d.enabled ? blocksMinutes(d.blocks) : 0), 0)

  const tabs: { id: Tab; label: string }[] = [
    { id: 'weekly', label: t('avail.weekly') },
    { id: 'exceptions', label: `${t('avail.exceptions')} · ${data.exceptions.length}` },
    { id: 'rules', label: t('avail.rules') },
    { id: 'preview', label: t('avail.preview') },
  ]

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('avail.title')} />

      {/* Live stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={t('avail.hours_week')} value={`${(weekMinutes / 60).toFixed(weekMinutes % 60 ? 1 : 0)}h`} />
        <Stat label={t('avail.active_days')} value={`${activeDays}/7`} />
        <Stat label={t('avail.default_slot')} value={`${data.rules.slot_minutes} min`} />
        <Stat label={t('avail.exceptions')} value={`${data.exceptions.length}`} />
      </div>

      <div className="flex gap-1 border-b border-line">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
              tab === tb.id ? 'border-accent text-accent' : 'border-transparent text-tx-3 hover:text-tx',
            )}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {tab === 'weekly' && (
        <WeeklyEditor
          weekly={data.weekly}
          onSave={async (weekly) => {
            try {
              await availabilityApi.updateWeekly(weekly)
              qc.invalidateQueries({ queryKey: ['availability'] })
              toast('Horario actualizado')
            } catch (err) {
              toast(errorMessage(err), 'danger')
            }
          }}
        />
      )}

      {tab === 'exceptions' && <ExceptionsTab exceptions={data.exceptions} />}

      {tab === 'rules' && (
        <RulesEditor
          rules={data.rules}
          onSave={async (rules) => {
            try {
              await availabilityApi.updateRules(rules)
              qc.invalidateQueries({ queryKey: ['availability'] })
              toast('Reglas actualizadas')
            } catch (err) {
              toast(errorMessage(err), 'danger')
            }
          }}
        />
      )}

      {tab === 'preview' && <PreviewTab />}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-tx-3">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-tx">{value}</p>
    </Card>
  )
}

function TimeSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md bg-transparent font-mono text-[13px] text-tx focus:outline-none"
    >
      {TIME_OPTIONS.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  )
}

/** Editable list of time blocks (SPEC PARTE E) — immutable updates, new block is editable. */
function BlockEditor({
  blocks,
  onChange,
}: {
  blocks: TimeRange[]
  onChange: (blocks: TimeRange[]) => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap items-center gap-2">
      {blocks.map((b, bi) => (
        <div key={bi} className="flex items-center gap-1.5 rounded-lg border border-line px-2 py-1">
          <TimeSelect
            value={b.start}
            onChange={(v) => onChange(blocks.map((x, xi) => (xi === bi ? { ...x, start: v } : x)))}
          />
          <span className="text-tx-4">–</span>
          <TimeSelect
            value={b.end}
            onChange={(v) => onChange(blocks.map((x, xi) => (xi === bi ? { ...x, end: v } : x)))}
          />
          <button
            type="button"
            onClick={() => onChange(blocks.filter((_, xi) => xi !== bi))}
            className="text-tx-4 hover:text-danger"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        // New block gets a sensible default and is immediately editable (never repeats
        // the previous one) — SPEC PARTE E.1/E.2.
        onClick={() => onChange([...blocks, { start: '14:00', end: '18:00' }])}
        className="flex items-center gap-1 rounded-lg border border-dashed border-line px-2 py-1 text-[13px] text-tx-3 hover:border-accent hover:text-accent"
      >
        <Plus className="h-3.5 w-3.5" />
        {t('avail.add_block')}
      </button>
    </div>
  )
}

function WeeklyEditor({ weekly, onSave }: { weekly: WeeklyDay[]; onSave: (weekly: WeeklyDay[]) => void }) {
  const t = useT()
  const [days, setDays] = useState<WeeklyDay[]>(() =>
    [...Array(7)].map(
      (_, i) => weekly.find((d) => d.day_of_week === i) ?? { day_of_week: i, enabled: false, blocks: [] },
    ),
  )

  function update(i: number, patch: Partial<WeeklyDay>) {
    setDays((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)))
  }

  return (
    <Card className="p-5">
      <div className="space-y-3">
        {days.map((day, i) => {
          const mins = blocksMinutes(day.blocks)
          return (
            <div key={i} className="flex items-start gap-4 border-b border-line-soft py-2.5 last:border-0">
              <label className="flex w-28 shrink-0 items-center gap-2 pt-1.5">
                <input
                  type="checkbox"
                  checked={day.enabled}
                  onChange={(e) => update(i, { enabled: e.target.checked })}
                  className="accent-accent"
                />
                <span className="text-sm font-medium text-tx">{DAYS[i]}</span>
              </label>
              {day.enabled ? (
                <div className="flex-1 space-y-1.5">
                  <BlockEditor blocks={day.blocks} onChange={(blocks) => update(i, { blocks })} />
                  <p className="text-[11px] text-tx-4">
                    {(mins / 60).toFixed(mins % 60 ? 1 : 0)}h · {day.blocks.length} {t('avail.blocks_label')}
                  </p>
                </div>
              ) : (
                <span className="pt-1.5 text-[13px] text-tx-4">{t('avail.not_working')}</span>
              )}
            </div>
          )
        })}
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={() => onSave(days)}>{t('app.save')}</Button>
      </div>
    </Card>
  )
}

function ExceptionsTab({ exceptions }: { exceptions: AvailabilityException[] }) {
  const t = useT()
  const qc = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)

  const remove = useMutation({
    mutationFn: (id: string) => availabilityApi.removeException(id),
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
      <ExceptionModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </Card>
  )
}

function ExceptionModal({ open, onClose }: { open: boolean; onClose: () => void }) {
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
      availabilityApi.addException({
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
          <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{t('avail.col_type')}</span>
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

function RulesEditor({ rules, onSave }: { rules: BookingRules; onSave: (rules: BookingRules) => void }) {
  const t = useT()
  const [form, setForm] = useState(rules)

  return (
    <Card className="max-w-xl p-5">
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('avail.slot_minutes')}
          value={form.slot_minutes}
          onChange={(e) => setForm({ ...form, slot_minutes: Number(e.target.value) })}
        >
          {[15, 20, 30, 45, 60].map((v) => (
            <option key={v} value={v}>
              {v} min
            </option>
          ))}
        </Select>
        <Input
          label={t('avail.min_advance')}
          type="number"
          min={0}
          value={form.min_advance_hours}
          onChange={(e) => setForm({ ...form, min_advance_hours: Number(e.target.value) })}
        />
      </div>
      <label className="mt-4 flex items-center gap-2 text-sm text-tx-2">
        <input
          type="checkbox"
          checked={form.allow_same_day}
          onChange={(e) => setForm({ ...form, allow_same_day: e.target.checked })}
          className="accent-accent"
        />
        {t('avail.same_day')}
      </label>
      <div className="mt-4 flex justify-end">
        <Button onClick={() => onSave(form)}>{t('app.save')}</Button>
      </div>
    </Card>
  )
}

function PreviewTab() {
  const t = useT()
  const weekStart = useMemo(
    () => format(startOfWeek(parseISO(clinicToday()), { weekStartsOn: 1 }), 'yyyy-MM-dd'),
    [],
  )

  const { data, isLoading } = useQuery({
    queryKey: ['availability', 'preview', weekStart],
    queryFn: () => availabilityApi.preview(weekStart),
  })

  if (isLoading) return <PageLoader />
  if (!data) return null

  const dayKeys = Object.keys(data).sort()
  // The fixed horizon gives every day the same time axis; take it from the first day.
  const times = (data[dayKeys[0]] ?? []).map((s) => s.start.slice(11, 16))

  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[13px] text-tx-3">{t('avail.preview_hint')}</p>
        <div className="flex items-center gap-3 text-[11px] text-tx-3">
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm bg-[var(--accent-10)]" />
            {t('avail.available')}
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm bg-surface-2" />
            {t('avail.unavailable')}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-center">
          <thead>
            <tr>
              <th className="w-14" />
              {dayKeys.map((d, i) => (
                <th key={d} className="px-1 py-1 text-[11px] font-medium text-tx-3">
                  {DAYS[i]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {times.map((time, ti) => (
              <tr key={time}>
                <td className="pr-2 text-right font-mono text-[10px] text-tx-4">{time}</td>
                {dayKeys.map((d) => {
                  const slot = data[d]?.[ti]
                  const available = slot && slot.status !== 'out_of_hours'
                  return (
                    <td key={d} className="px-0.5 py-0.5">
                      <div
                        className={cn(
                          'h-4 rounded-sm',
                          available ? 'bg-[var(--accent-10)]' : 'bg-surface-2',
                        )}
                        title={slot ? `${time} · ${slot.status}` : time}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

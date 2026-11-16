import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Input'
import { useT } from '@/lib/i18n'
import type { TimeRange, WeeklyDay } from '@/types'
import { DAY_KEYS, TIME_OPTIONS, blocksMinutes } from './schedule'

function TimeSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select
      variant="bare"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-auto gap-1 font-mono text-[13px]"
    >
      {TIME_OPTIONS.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </Select>
  )
}

/** Editable list of time blocks (SPEC PARTE E) — immutable updates, new block is editable. */
export function BlockEditor({
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

export function WeeklyEditor({
  weekly,
  onSave,
}: {
  weekly: WeeklyDay[]
  onSave: (weekly: WeeklyDay[]) => void
}) {
  const t = useT()
  const [days, setDays] = useState<WeeklyDay[]>(() =>
    [...Array(7)].map(
      (_, i) =>
        weekly.find((d) => d.day_of_week === i) ?? { day_of_week: i, enabled: false, blocks: [] },
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
            <div
              key={i}
              className="flex items-start gap-4 border-b border-line-soft py-2.5 last:border-0"
            >
              <label className="flex w-28 shrink-0 items-center gap-2 pt-1.5">
                <input
                  type="checkbox"
                  checked={day.enabled}
                  onChange={(e) => update(i, { enabled: e.target.checked })}
                  className="accent-accent"
                />
                <span className="text-sm font-medium text-tx">{t(DAY_KEYS[i])}</span>
              </label>
              {day.enabled ? (
                <div className="flex-1 space-y-1.5">
                  <BlockEditor blocks={day.blocks} onChange={(blocks) => update(i, { blocks })} />
                  <p className="text-[11px] text-tx-4">
                    {(mins / 60).toFixed(mins % 60 ? 1 : 0)}h · {day.blocks.length}{' '}
                    {t('avail.blocks_label')}
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

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { availabilityApi } from '@/api/availability'
import { errorMessage } from '@/api/client'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import type { BookingRules, WeeklyDay } from '@/types'

const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
type Tab = 'weekly' | 'rules'

export function AvailabilityPage() {
  const t = useT()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('weekly')

  const { data, isLoading } = useQuery({
    queryKey: ['availability', 'me'],
    queryFn: () => availabilityApi.getMine(),
  })

  if (isLoading || !data) return <PageLoader />

  const tabs: { id: Tab; label: string }[] = [
    { id: 'weekly', label: t('avail.weekly') },
    { id: 'rules', label: t('avail.rules') },
  ]

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('avail.title')} />

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
    </div>
  )
}

function WeeklyEditor({
  weekly,
  onSave,
}: {
  weekly: WeeklyDay[]
  onSave: (weekly: WeeklyDay[]) => void
}) {
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
        {days.map((day, i) => (
          <div key={i} className="flex items-center gap-4 border-b border-line-soft py-2 last:border-0">
            <label className="flex w-28 items-center gap-2">
              <input
                type="checkbox"
                checked={day.enabled}
                onChange={(e) => update(i, { enabled: e.target.checked })}
                className="accent-accent"
              />
              <span className="text-sm font-medium text-tx">{DAYS[i]}</span>
            </label>
            {day.enabled ? (
              <div className="flex flex-1 flex-wrap items-center gap-2">
                {day.blocks.map((b, bi) => (
                  <div key={bi} className="flex items-center gap-1.5 rounded-lg border border-line px-2 py-1">
                    <input
                      type="time"
                      value={b.start}
                      onChange={(e) =>
                        update(i, {
                          blocks: day.blocks.map((x, xi) =>
                            xi === bi ? { ...x, start: e.target.value } : x,
                          ),
                        })
                      }
                      className="bg-transparent font-mono text-[13px] text-tx focus:outline-none"
                    />
                    <span className="text-tx-4">–</span>
                    <input
                      type="time"
                      value={b.end}
                      onChange={(e) =>
                        update(i, {
                          blocks: day.blocks.map((x, xi) =>
                            xi === bi ? { ...x, end: e.target.value } : x,
                          ),
                        })
                      }
                      className="bg-transparent font-mono text-[13px] text-tx focus:outline-none"
                    />
                    <button
                      onClick={() =>
                        update(i, { blocks: day.blocks.filter((_, xi) => xi !== bi) })
                      }
                      className="text-tx-4 hover:text-danger"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    update(i, { blocks: [...day.blocks, { start: '09:00', end: '13:00' }] })
                  }
                  className="flex items-center gap-1 rounded-lg border border-dashed border-line px-2 py-1 text-[13px] text-tx-3 hover:border-accent hover:text-accent"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Bloque
                </button>
              </div>
            ) : (
              <span className="text-[13px] text-tx-4">No disponible</span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={() => onSave(days)}>{t('app.save')}</Button>
      </div>
    </Card>
  )
}

function RulesEditor({
  rules,
  onSave,
}: {
  rules: BookingRules
  onSave: (rules: BookingRules) => void
}) {
  const t = useT()
  const [form, setForm] = useState(rules)

  return (
    <Card className="max-w-xl p-5">
      <div className="grid grid-cols-2 gap-4">
        <Input
          label={t('avail.slot_minutes')}
          type="number"
          value={form.slot_minutes}
          onChange={(e) => setForm({ ...form, slot_minutes: Number(e.target.value) })}
        />
        <Input
          label={t('avail.buffer')}
          type="number"
          value={form.buffer_minutes}
          onChange={(e) => setForm({ ...form, buffer_minutes: Number(e.target.value) })}
        />
        <Input
          label={t('avail.min_advance')}
          type="number"
          value={form.min_advance_hours}
          onChange={(e) => setForm({ ...form, min_advance_hours: Number(e.target.value) })}
        />
        <Input
          label={t('avail.max_advance')}
          type="number"
          value={form.max_advance_days}
          onChange={(e) => setForm({ ...form, max_advance_days: Number(e.target.value) })}
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

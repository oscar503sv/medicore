import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { useT } from '@/lib/i18n'
import type { BookingRules } from '@/types'

export function RulesEditor({
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

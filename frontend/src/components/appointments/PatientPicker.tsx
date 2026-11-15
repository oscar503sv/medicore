import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { patientsApi } from '@/api/patients'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import type { Patient } from '@/types'

/** Search box plus a short result list; the chosen patient is highlighted. */
export function PatientPicker({
  selected,
  onSelect,
}: {
  selected: Patient | null
  onSelect: (patient: Patient) => void
}) {
  const t = useT()
  const [search, setSearch] = useState('')
  const { data: patients } = useQuery({
    queryKey: ['patients', { q: search }],
    queryFn: () => patientsApi.list({ q: search || undefined, limit: 8 }),
  })

  return (
    <div className="space-y-3">
      <Input
        placeholder={t('appt.select_patient')}
        aria-label={t('appt.select_patient')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        autoFocus
      />
      <div className="max-h-60 space-y-1 overflow-y-auto">
        {patients?.items.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-pressed={selected?.id === p.id}
            onClick={() => onSelect(p)}
            className={cn(
              'flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-left transition-colors',
              selected?.id === p.id
                ? 'border-accent bg-[var(--accent-10)]'
                : 'border-line hover:bg-surface-2',
            )}
          >
            <div>
              <p className="text-sm font-medium text-tx">
                {p.first_name} {p.last_name}
              </p>
              <p className="font-mono text-xs text-tx-3">{p.code}</p>
            </div>
            {selected?.id === p.id && <Check className="h-4 w-4 text-accent" />}
          </button>
        ))}
      </div>
    </div>
  )
}

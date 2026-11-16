import type { Slot } from '@/types'
import { cn } from '@/lib/cn'
import { fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'

/** Day's slots for the picked assignee; only free ones can be chosen. */
export function SlotGrid({
  slots,
  isLoading,
  selected,
  onSelect,
  offDayMessage,
}: {
  slots: Slot[] | undefined
  isLoading: boolean
  selected: Slot | null
  onSelect: (slot: Slot) => void
  /** Shown when nothing is bookable that day (off exception or non-working weekday). */
  offDayMessage: string
}) {
  const t = useT()
  if (isLoading) return <p className="py-10 text-center text-sm text-tx-3">…</p>
  if (!slots || slots.length === 0)
    return <p className="py-10 text-center text-sm text-tx-3">{t('appt.no_slots')}</p>
  if (slots.every((s) => s.status === 'out_of_hours'))
    return <p className="py-10 text-center text-sm text-tx-3">{offDayMessage}</p>
  return (
    <div className="grid max-h-[240px] grid-cols-4 gap-2 overflow-y-auto pr-1">
      {slots.map((slot) => {
        const isFree = slot.status === 'free'
        const isSelected = selected?.start === slot.start
        const titleKey =
          slot.status === 'out_of_hours'
            ? 'appt.slot_out'
            : slot.status === 'blocked_rules'
              ? 'appt.slot_blocked'
              : `appt.slot_${slot.status}`
        return (
          <button
            key={slot.start}
            type="button"
            disabled={!isFree}
            aria-pressed={isFree ? isSelected : undefined}
            onClick={() => onSelect(slot)}
            className={cn(
              'rounded-lg border py-2 font-mono text-[13px] transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
              isFree && isSelected && 'border-accent bg-accent text-white shadow-sm',
              isFree &&
                !isSelected &&
                'border-accent bg-[var(--accent-10)] text-tx hover:bg-accent hover:text-white',
              slot.status === 'taken' && 'border-line-soft text-tx-4 line-through',
              (slot.status === 'out_of_hours' || slot.status === 'blocked_rules') &&
                'cursor-not-allowed border-line-soft bg-surface-2 text-tx-4',
            )}
            title={t(titleKey)}
          >
            {fmtTime(slot.start)}
          </button>
        )
      })}
    </div>
  )
}

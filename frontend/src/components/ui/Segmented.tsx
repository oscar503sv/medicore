import { cn } from '@/lib/cn'

export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-surface p-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            'rounded-lg px-3 py-1.5 text-[13px] font-medium leading-none transition-colors',
            value === opt.value ? 'bg-accent text-white shadow-sm' : 'text-tx-2 hover:text-tx',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

import { format, parseISO } from 'date-fns'
import { enUS, es } from 'date-fns/locale'
import { useUIStore } from '@/stores/ui'

function locale() {
  return useUIStore.getState().lang === 'es' ? es : enUS
}

export function fmtDate(iso: string | null | undefined, pattern = 'd MMM yyyy'): string {
  if (!iso) return '—'
  return format(parseISO(iso), pattern, { locale: locale() })
}

/** Format the current date/time with the active locale (e.g. dashboard header). */
export function fmtNow(pattern: string): string {
  return format(new Date(), pattern, { locale: locale() })
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return format(parseISO(iso), 'HH:mm')
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return format(parseISO(iso), 'd MMM · HH:mm', { locale: locale() })
}

/** "HH:mm" range from a Date for slot grids. */
export function fmtClock(date: Date): string {
  return format(date, 'HH:mm')
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

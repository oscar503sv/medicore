import { format, parseISO } from 'date-fns'
import { enUS, es } from 'date-fns/locale'
import { formatInTimeZone } from 'date-fns-tz'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'

function locale() {
  return useUIStore.getState().lang === 'es' ? es : enUS
}

/** The clinic's IANA timezone (from the session), falling back to the browser's. */
function clinicTz(): string {
  return useAuthStore.getState().session?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
}

// ── Wall-clock values (appointment/slot times, next/last visit) ──────────────────
// These come from the backend as naive ISO (no offset); parseISO + format renders the
// literal wall-clock in any browser timezone.

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

// ── Event instants (created/updated, signed, encounter, last seen, audit) ────────
// These are true UTC instants; render them in the clinic's timezone so they read the same
// regardless of where the viewer's browser is.

export function fmtDateTz(iso: string | null | undefined, pattern = 'd MMM yyyy'): string {
  if (!iso) return '—'
  return formatInTimeZone(iso, clinicTz(), pattern, { locale: locale() })
}

export function fmtDateTimeTz(iso: string | null | undefined): string {
  if (!iso) return '—'
  return formatInTimeZone(iso, clinicTz(), 'd MMM · HH:mm', { locale: locale() })
}

export function fmtTimeTz(iso: string | null | undefined): string {
  if (!iso) return '—'
  return formatInTimeZone(iso, clinicTz(), 'HH:mm')
}

/** Today's date (yyyy-MM-dd) in the clinic's timezone — for agenda/day defaults. */
export function clinicToday(): string {
  return formatInTimeZone(new Date(), clinicTz(), 'yyyy-MM-dd')
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

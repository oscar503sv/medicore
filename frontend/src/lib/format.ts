import { format, formatDistanceStrict, formatDistanceToNowStrict, parseISO } from 'date-fns'
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

/** "hace 5 minutos" / "5 minutes ago" — timezone-independent, for recent events. */
export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  return formatDistanceToNowStrict(parseISO(iso), { addSuffix: true, locale: locale() })
}

/** A span of time in words ("3 días" / "3 days"), e.g. a process uptime. */
export function fmtDuration(seconds: number): string {
  return formatDistanceStrict(0, seconds * 1000, { locale: locale() })
}

/** Bytes in the largest fitting unit ("12.4 MB"). */
export function fmtBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit === 0 || value >= 100 ? 0 : 1)} ${units[unit]}`
}

/** Today's date (yyyy-MM-dd) in the clinic's timezone — for agenda/day defaults. */
export function clinicToday(): string {
  return formatInTimeZone(new Date(), clinicTz(), 'yyyy-MM-dd')
}

/** Current wall-clock time (HH:mm) in the clinic's timezone — for "now" markers. */
export function clinicNowTime(): string {
  return formatInTimeZone(new Date(), clinicTz(), 'HH:mm')
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

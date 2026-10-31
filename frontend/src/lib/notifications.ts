import {
  CalendarClock,
  CalendarPlus,
  CalendarX,
  FilePen,
  Paperclip,
  UserCheck,
  UserPlus,
  UserX,
  Bell,
  type LucideIcon,
} from 'lucide-react'
import type { Tone } from '@/components/ui/badgeTone'
import { fmtDateTime } from '@/lib/format'
import type { AppNotification } from '@/types'

type T = (key: string) => string

interface NotificationView {
  icon: LucideIcon
  tone: Tone
  text: string
  /** Where clicking the notification takes the user, if anywhere. */
  href: string | null
}

const META: Record<string, { icon: LucideIcon; tone: Tone }> = {
  'appointment.created': { icon: CalendarPlus, tone: 'info' },
  'appointment.rescheduled': { icon: CalendarClock, tone: 'warn' },
  'appointment.cancelled': { icon: CalendarX, tone: 'danger' },
  'appointment.no_show': { icon: UserX, tone: 'warn' },
  'record.amended': { icon: FilePen, tone: 'accent' },
  'document.uploaded': { icon: Paperclip, tone: 'neutral' },
  'user.created': { icon: UserPlus, tone: 'ok' },
  'user.role_changed': { icon: UserCheck, tone: 'warn' },
}

/** Translate `key`, falling back to `fallback` when the key is missing. */
function tr(t: T, key: string, fallback: string): string {
  const label = t(key)
  return label === key ? fallback : label
}

/** Fill `{name}` placeholders; missing values render as an em dash. */
function fill(template: string, values: Record<string, string | undefined>): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => values[k] || '—')
}

function hrefFor(n: AppNotification): string | null {
  const d = n.data
  if (n.type.startsWith('appointment.')) {
    // scheduled_start is a naive clinic wall-clock ISO, so its date part is the agenda day.
    const day = d.scheduled_start?.slice(0, 10)
    return day ? `/appointments?date=${day}` : '/appointments'
  }
  if (n.type === 'record.amended' && d.patient_id) {
    const record = d.record_id ? `&record=${d.record_id}` : ''
    return `/patients/${d.patient_id}?tab=history${record}`
  }
  if (n.type === 'document.uploaded' && d.patient_id) {
    return `/patients/${d.patient_id}?tab=documents`
  }
  if (n.type.startsWith('user.')) return '/users'
  return null
}

/** Icon, colour, localized sentence and link target for a notification. */
export function describeNotification(t: T, n: AppNotification): NotificationView {
  const d = n.data
  const values = {
    actor: d.actor_name || t('notif.someone'),
    patient: d.patient_name,
    when: d.scheduled_start ? fmtDateTime(d.scheduled_start) : undefined,
    previous: d.previous_start ? fmtDateTime(d.previous_start) : undefined,
    code: d.record_code,
    kind: d.kind ? tr(t, `docs.kind_${d.kind}`, d.kind) : undefined,
    user: d.user_name,
    role: d.role ? tr(t, `role.${d.role}`, d.role) : undefined,
    previous_role: d.previous_role ? tr(t, `role.${d.previous_role}`, d.previous_role) : undefined,
  }
  const template = tr(t, `notif.type.${n.type}`, n.type)
  return {
    ...(META[n.type] ?? { icon: Bell, tone: 'neutral' as Tone }),
    text: fill(template, values),
    href: hrefFor(n),
  }
}

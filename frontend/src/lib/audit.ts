import {
  Activity,
  Building2,
  CalendarDays,
  Clock,
  FileText,
  LifeBuoy,
  LogIn,
  MapPin,
  Paperclip,
  Shield,
  Stethoscope,
  UserRound,
  Users,
  type LucideIcon,
} from 'lucide-react'
import type { Tone } from '@/components/ui/badgeTone'

type T = (key: string) => string

/** Action categories offered in the audit filters (the action namespace before the dot). */
export const AUDIT_CATEGORIES = [
  'auth',
  'patient',
  'appointment',
  'consultation',
  'record',
  'document',
  'user',
  'insurer',
  'availability',
  'organization',
  'location',
  'tenant',
  'support',
] as const

/** Human label for an action, translated via `audit.action.<action>`, falling back to raw. */
export function actionLabel(t: T, action: string): string {
  const key = `audit.action.${action}`
  const label = t(key)
  return label === key ? action : label
}

/** Human label for an entity type, translated via `audit.entity.<type>`, falling back to raw. */
export function entityLabel(t: T, entityType: string): string {
  const key = `audit.entity.${entityType}`
  const label = t(key)
  return label === key ? entityType : label
}

/** The action namespace before the dot (e.g. "appointment.created" → "appointment"). */
export function categoryOf(action: string): string {
  return action.split('.')[0]
}

/** Icon + colour tone per action category, for quick visual scanning of the log. */
const CATEGORY_META: Record<string, { icon: LucideIcon; tone: Tone }> = {
  auth: { icon: LogIn, tone: 'info' },
  patient: { icon: UserRound, tone: 'accent' },
  appointment: { icon: CalendarDays, tone: 'info' },
  consultation: { icon: Stethoscope, tone: 'ok' },
  record: { icon: FileText, tone: 'accent' },
  document: { icon: Paperclip, tone: 'neutral' },
  user: { icon: Users, tone: 'warn' },
  insurer: { icon: Shield, tone: 'info' },
  availability: { icon: Clock, tone: 'neutral' },
  organization: { icon: Building2, tone: 'warn' },
  location: { icon: MapPin, tone: 'warn' },
  tenant: { icon: Building2, tone: 'warn' },
  support: { icon: LifeBuoy, tone: 'danger' },
}

export function categoryMeta(action: string): { icon: LucideIcon; tone: Tone } {
  return CATEGORY_META[categoryOf(action)] ?? { icon: Activity, tone: 'neutral' }
}

/**
 * A short, human-readable summary of an entry's metadata for the "Detail" column.
 * Surfaces only meaningful fields (status transitions, reason, role, names); returns '' when
 * there's nothing useful — never a raw UUID. Works for both tenant and global audit entries.
 */
export function auditDetail(e: { metadata?: Record<string, unknown> }): string {
  const m = e.metadata ?? {}
  const parts: string[] = []
  // Human subject (e.g. "P-00013 · Lucía Álvarez") recorded at write time — shown first.
  if (typeof m.subject === 'string' && m.subject) parts.push(m.subject)
  if (typeof m.old_status === 'string' && typeof m.new_status === 'string') {
    parts.push(`${m.old_status} → ${m.new_status}`)
  } else if (typeof m.status === 'string') {
    parts.push(m.status)
  }
  if (typeof m.reason === 'string' && m.reason) parts.push(m.reason)
  if (typeof m.role === 'string') parts.push(m.role)
  if (typeof m.name === 'string') parts.push(m.name)
  if (typeof m.email === 'string') parts.push(m.email)
  if (typeof m.slug === 'string') parts.push(m.slug)
  return parts.join(' · ')
}

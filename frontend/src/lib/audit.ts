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

/**
 * A short, human-readable summary of an entry's metadata for the "Detail" column.
 * Surfaces only meaningful fields (status transitions, reason, role, names); returns '' when
 * there's nothing useful — never a raw UUID. Works for both tenant and global audit entries.
 */
export function auditDetail(e: { metadata?: Record<string, unknown> }): string {
  const m = e.metadata ?? {}
  const parts: string[] = []
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

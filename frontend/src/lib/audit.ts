import type { AuditEntry } from '@/types'

type T = (key: string) => string

/** Action categories offered in the audit filters (the action namespace before the dot). */
export const AUDIT_CATEGORIES = [
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

/** A short, readable summary of an entry's metadata for the "Detail" column. */
export function auditDetail(t: T, e: AuditEntry): string {
  const m = e.metadata ?? {}
  const parts: string[] = []
  if (typeof m.old_status === 'string' && typeof m.new_status === 'string') {
    parts.push(`${m.old_status} → ${m.new_status}`)
  } else if (typeof m.status === 'string') {
    parts.push(String(m.status))
  }
  if (typeof m.reason === 'string' && m.reason) parts.push(String(m.reason))
  if (typeof m.role === 'string') parts.push(String(m.role))
  if (typeof m.name === 'string') parts.push(String(m.name))
  if (parts.length === 0) parts.push(`${entityLabel(t, e.entity_type)} · ${e.entity_id.slice(0, 8)}`)
  return parts.join(' · ')
}

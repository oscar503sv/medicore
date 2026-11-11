import {
  Activity,
  BadgeDollarSign,
  Building2,
  MapPin,
  CalendarDays,
  Clock,
  FileText,
  KeyRound,
  Pill,
  ScrollText,
  ShieldCheck,
  Stethoscope,
  Syringe,
  UserCog,
  Users,
} from 'lucide-react'
import type { Permission } from '@/types'

// Clinical/legal guardrail mirrored from the backend: only doctors may hold these,
// and they cannot be taken away from them.
export const DOCTOR_ONLY: Permission[] = ['records.sign', 'records.amend']

// Mirrored from the backend: handing out permissions stays with administrators.
export const ADMIN_ONLY: Permission[] = ['permissions.manage']

/** Fixed for this role: neither granted nor removed by a customization. */
export function isFixedFor(role: string, permission: Permission): boolean {
  return DOCTOR_ONLY.includes(permission) || (role !== 'admin' && ADMIN_ONLY.includes(permission))
}

export const GROUP_ICONS: Record<string, typeof Users> = {
  patients: Users,
  appointments: CalendarDays,
  availability: Clock,
  fees: BadgeDollarSign,
  consultations: Stethoscope,
  records: FileText,
  prescriptions: Pill,
  diagnoses: Activity,
  insurers: ShieldCheck,
  users: UserCog,
  organization: Building2,
  locations: MapPin,
  audit: ScrollText,
  permissions: KeyRound,
  vaccinations: Syringe,
  applications: Pill,
  procedures: Activity,
}

/** The catalog grouped by resource (the part before the dot), in catalog order. */
export function groupByResource(catalog: Permission[]): [string, Permission[]][] {
  const byResource = new Map<string, Permission[]>()
  for (const p of catalog) {
    const resource = p.split('.')[0]
    byResource.set(resource, [...(byResource.get(resource) ?? []), p])
  }
  return [...byResource.entries()]
}

export function sameSet(a: Permission[], b: Permission[]) {
  return a.length === b.length && a.every((p) => b.includes(p))
}

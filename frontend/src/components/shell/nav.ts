import {
  Activity,
  Calendar,
  CalendarDays,
  FileText,
  KeyRound,
  LayoutDashboard,
  type LucideIcon,
  Pill,
  ScrollText,
  Settings,
  ShieldCheck,
  Stethoscope,
  Syringe,
  Users,
  UsersRound,
} from 'lucide-react'
import type { Permission, Role } from '@/types'

export type NavGroup = 'general' | 'clinical' | 'management'

export interface NavItem {
  to: string
  labelKey: string
  icon: LucideIcon
  // Visibility gates (both must pass when present; an item with neither is visible to all):
  permission?: Permission // capability-based gate, matches the backend catalog
  roles?: Role[] // role-based gate, for pages tied to an identity rather than a capability
  group: NavGroup
  comingSoon?: boolean // future module: shown with a "Próximamente" badge, placeholder page
}

export const NAV_GROUPS: { id: NavGroup; labelKey: string }[] = [
  { id: 'general', labelKey: 'nav.group_general' },
  { id: 'clinical', labelKey: 'nav.group_clinical' },
  { id: 'management', labelKey: 'nav.group_management' },
]

export const NAV_ITEMS: NavItem[] = [
  // General
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, group: 'general' },
  // Clínico
  { to: '/patients', labelKey: 'nav.patients', icon: Users, permission: 'patients.view', group: 'clinical' },
  { to: '/appointments', labelKey: 'nav.appointments', icon: Calendar, permission: 'appointments.view', group: 'clinical' },
  { to: '/schedule', labelKey: 'nav.schedule', icon: CalendarDays, permission: 'appointments.view', group: 'clinical' },
  { to: '/records', labelKey: 'nav.records', icon: FileText, permission: 'records.view', group: 'clinical' },
  { to: '/applications', labelKey: 'nav.applications', icon: Pill, roles: ['doctor', 'nurse'], group: 'clinical', comingSoon: true },
  { to: '/procedures', labelKey: 'nav.procedures', icon: Activity, roles: ['doctor', 'nurse'], group: 'clinical', comingSoon: true },
  { to: '/vaccination', labelKey: 'nav.vaccination', icon: Syringe, roles: ['doctor', 'nurse'], group: 'clinical', comingSoon: true },
  // Gestión
  // "Mi disponibilidad" is the doctor's own agenda; admins hold availability.manage but
  // have no doctor schedule of their own, so this stays role-gated.
  { to: '/availability', labelKey: 'nav.availability', icon: Stethoscope, roles: ['doctor'], group: 'management' },
  { to: '/users', labelKey: 'nav.users', icon: UsersRound, permission: 'users.manage', group: 'management' },
  { to: '/permissions', labelKey: 'nav.permissions', icon: KeyRound, permission: 'permissions.manage', group: 'management' },
  { to: '/insurers', labelKey: 'nav.insurers', icon: ShieldCheck, permission: 'insurers.manage', group: 'management' },
  { to: '/audit', labelKey: 'nav.audit', icon: ScrollText, permission: 'audit.view', group: 'management' },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, group: 'management' },
]

import {
  Calendar,
  CalendarDays,
  FileText,
  LayoutDashboard,
  type LucideIcon,
  Settings,
  ShieldCheck,
  Stethoscope,
  Users,
  UsersRound,
} from 'lucide-react'
import type { Role } from '@/types'

export type NavGroup = 'general' | 'clinical' | 'management'

export interface NavItem {
  to: string
  labelKey: string
  icon: LucideIcon
  roles: Role[] // which roles see this item
  group: NavGroup
}

export const NAV_GROUPS: { id: NavGroup; labelKey: string }[] = [
  { id: 'general', labelKey: 'nav.group_general' },
  { id: 'clinical', labelKey: 'nav.group_clinical' },
  { id: 'management', labelKey: 'nav.group_management' },
]

export const NAV_ITEMS: NavItem[] = [
  // General
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, roles: ['admin', 'doctor', 'nurse', 'receptionist'], group: 'general' },
  // Clínico
  { to: '/patients', labelKey: 'nav.patients', icon: Users, roles: ['admin', 'doctor', 'nurse', 'receptionist'], group: 'clinical' },
  { to: '/appointments', labelKey: 'nav.appointments', icon: Calendar, roles: ['admin', 'doctor', 'nurse', 'receptionist'], group: 'clinical' },
  { to: '/schedule', labelKey: 'nav.schedule', icon: CalendarDays, roles: ['admin', 'doctor', 'nurse', 'receptionist'], group: 'clinical' },
  { to: '/records', labelKey: 'nav.records', icon: FileText, roles: ['admin', 'doctor', 'nurse'], group: 'clinical' },
  // Gestión
  { to: '/availability', labelKey: 'nav.availability', icon: Stethoscope, roles: ['doctor'], group: 'management' },
  { to: '/users', labelKey: 'nav.users', icon: UsersRound, roles: ['admin'], group: 'management' },
  { to: '/insurers', labelKey: 'nav.insurers', icon: ShieldCheck, roles: ['admin'], group: 'management' },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, roles: ['admin', 'doctor', 'nurse', 'receptionist'], group: 'management' },
]

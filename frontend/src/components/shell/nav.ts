import {
  Calendar,
  CalendarDays,
  FileText,
  LayoutDashboard,
  type LucideIcon,
  Settings,
  Stethoscope,
  Users,
  UsersRound,
} from 'lucide-react'
import type { Role } from '@/types'

export interface NavItem {
  to: string
  labelKey: string
  icon: LucideIcon
  roles: Role[] // which roles see this item
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
  { to: '/patients', labelKey: 'nav.patients', icon: Users, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
  { to: '/appointments', labelKey: 'nav.appointments', icon: Calendar, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
  { to: '/schedule', labelKey: 'nav.schedule', icon: CalendarDays, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
  { to: '/records', labelKey: 'nav.records', icon: FileText, roles: ['admin', 'doctor', 'nurse'] },
  { to: '/availability', labelKey: 'nav.availability', icon: Stethoscope, roles: ['doctor', 'admin'] },
  { to: '/users', labelKey: 'nav.users', icon: UsersRound, roles: ['admin'] },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
]

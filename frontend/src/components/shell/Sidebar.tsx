import { NavLink } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { NAV_ITEMS } from './nav'

export function Sidebar() {
  const t = useT()
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggle = useUIStore((s) => s.toggleSidebar)
  const role = useAuthStore((s) => s.session?.role)

  const items = NAV_ITEMS.filter((item) => role && item.roles.includes(role))

  return (
    <aside
      className={cn(
        'flex shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200',
        collapsed ? 'w-14' : 'w-60',
      )}
    >
      {/* Logo + collapse toggle */}
      <div className="flex h-14 items-center justify-between border-b border-line px-3">
        {collapsed ? (
          <button
            onClick={toggle}
            className="mx-auto flex h-8 w-8 items-center justify-center rounded-lg bg-accent font-serif text-lg text-white"
          >
            M
          </button>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent font-serif text-lg text-white">
                M
              </span>
              <span className="font-serif text-lg text-tx">Medicore</span>
            </div>
            <button
              onClick={toggle}
              className="rounded-md p-1 text-tx-3 hover:bg-surface-2"
              aria-label="Collapse sidebar"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 p-2">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors',
                isActive
                  ? 'bg-[var(--accent-10)] text-accent'
                  : 'text-tx-2 hover:bg-surface-2 hover:text-tx',
                collapsed && 'justify-center px-0',
              )
            }
            title={collapsed ? t(item.labelKey) : undefined}
          >
            <item.icon className="h-[18px] w-[18px] shrink-0" />
            {!collapsed && <span>{t(item.labelKey)}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

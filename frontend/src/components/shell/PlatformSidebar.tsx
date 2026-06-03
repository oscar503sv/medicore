import { NavLink } from 'react-router-dom'
import { BarChart3, Building2, ChevronLeft, ScrollText, ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { useUIStore } from '@/stores/ui'

const NAV = [
  { to: '/platform/clinics', labelKey: 'platform.nav_clinics', icon: Building2 },
  { to: '/platform/stats', labelKey: 'platform.nav_stats', icon: BarChart3 },
  { to: '/platform/audit', labelKey: 'platform.nav_audit', icon: ScrollText },
]

export function PlatformSidebar() {
  const t = useT()
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggle = useUIStore((s) => s.toggleSidebar)

  return (
    <aside
      className={cn(
        'flex shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200',
        collapsed ? 'w-14' : 'w-60',
      )}
    >
      {/* Brand + collapse toggle */}
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
            <div className="flex min-w-0 items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent font-serif text-lg text-white">
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

      {/* Platform context */}
      {!collapsed && (
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-2 text-tx-2">
            <ShieldAlert className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium leading-tight text-tx">
              {t('platform.console')}
            </p>
          </div>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
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

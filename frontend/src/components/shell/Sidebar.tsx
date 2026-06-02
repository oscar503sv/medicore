import { NavLink } from 'react-router-dom'
import { Building2, ChevronLeft } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { NAV_GROUPS, NAV_ITEMS } from './nav'

export function Sidebar() {
  const t = useT()
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggle = useUIStore((s) => s.toggleSidebar)
  const role = useAuthStore((s) => s.session?.role)
  const tenantName = useAuthStore((s) => s.session?.tenant_name)

  const visible = NAV_ITEMS.filter((item) => role && item.roles.includes(role))

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

      {/* Tenant / organization */}
      {!collapsed && tenantName && (
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-2 text-tx-2">
            <Building2 className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium leading-tight text-tx">{tenantName}</p>
            <p className="text-[11px] text-tx-3">{t('nav.organization')}</p>
          </div>
        </div>
      )}

      {/* Nav grouped by category */}
      <nav className="flex-1 space-y-4 overflow-y-auto p-2">
        {NAV_GROUPS.map((group) => {
          const items = visible.filter((item) => item.group === group.id)
          if (items.length === 0) return null
          return (
            <div key={group.id} className="space-y-0.5">
              {!collapsed && (
                <p className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-tx-4">
                  {t(group.labelKey)}
                </p>
              )}
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
            </div>
          )
        })}
      </nav>
    </aside>
  )
}

import { LogOut, Building2, BarChart3, ScrollText, ShieldAlert } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { usePlatformAuthStore } from '@/stores/platformAuth'

const NAV = [
  { to: '/platform/clinics', labelKey: 'platform.nav_clinics', icon: Building2 },
  { to: '/platform/stats', labelKey: 'platform.nav_stats', icon: BarChart3 },
  { to: '/platform/audit', labelKey: 'platform.nav_audit', icon: ScrollText },
]

export function PlatformLayout() {
  const t = useT()
  const navigate = useNavigate()
  const session = usePlatformAuthStore((s) => s.session)
  const logout = usePlatformAuthStore((s) => s.logout)

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-surface">
        <div className="flex h-14 items-center gap-2.5 border-b border-line px-4">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent">
            <ShieldAlert className="h-4 w-4 text-white" />
          </span>
          <div className="min-w-0">
            <p className="font-serif text-base leading-tight text-tx">Medicore</p>
            <p className="text-[11px] text-tx-3">{t('platform.console')}</p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 p-2">
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
                )
              }
            >
              <item.icon className="h-[18px] w-[18px] shrink-0" />
              <span>{t(item.labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line p-3">
          <p className="truncate px-2 text-[13px] font-medium text-tx">{session?.name}</p>
          <p className="truncate px-2 text-[11px] text-tx-3">{session?.email}</p>
          <button
            onClick={() => {
              logout()
              navigate('/platform/login')
            }}
            className="mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13px] font-medium text-tx-2 transition-colors hover:bg-surface-2 hover:text-tx"
          >
            <LogOut className="h-[18px] w-[18px]" />
            {t('platform.logout')}
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}

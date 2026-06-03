import {
  LogOut,
  Building2,
  BarChart3,
  ScrollText,
  ShieldAlert,
  Monitor,
  Moon,
  Sun,
} from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { usePlatformAuthStore } from '@/stores/platformAuth'
import { useUIStore, type Theme } from '@/stores/ui'

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
  const { theme, setTheme, lang, setLang } = useUIStore()

  const themeIcons: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Monitor }
  const ThemeIcon = themeIcons[theme]
  const cycleTheme = () => {
    const order: Theme[] = ['light', 'dark', 'system']
    setTheme(order[(order.indexOf(theme) + 1) % order.length])
  }

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

        <div className="flex items-center justify-between border-t border-line px-3 py-2">
          <div className="flex items-center rounded-pill border border-line p-0.5">
            {(['es', 'en'] as const).map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => setLang(l)}
                aria-pressed={lang === l}
                className={cn(
                  'rounded-pill px-2.5 py-1 text-xs font-medium transition-colors',
                  lang === l ? 'bg-surface-2 text-tx' : 'text-tx-3 hover:text-tx',
                )}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            onClick={cycleTheme}
            title={theme}
            aria-label="Cambiar tema"
            className="rounded-md p-2 text-tx-2 transition-colors hover:bg-surface-2 hover:text-tx"
          >
            <ThemeIcon className="h-[18px] w-[18px]" />
          </button>
        </div>

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

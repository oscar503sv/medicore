import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, LogOut, Monitor, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { usePlatformAuthStore } from '@/stores/platformAuth'
import { useUIStore, type Theme } from '@/stores/ui'
import { Avatar } from '@/components/ui/Avatar'

export function PlatformTopbar() {
  const t = useT()
  const navigate = useNavigate()
  const session = usePlatformAuthStore((s) => s.session)
  const logout = usePlatformAuthStore((s) => s.logout)
  const { theme, setTheme, lang, setLang } = useUIStore()
  const [menuOpen, setMenuOpen] = useState(false)

  const themeIcons: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Monitor }
  const ThemeIcon = themeIcons[theme]
  const cycleTheme = () => {
    const order: Theme[] = ['light', 'dark', 'system']
    setTheme(order[(order.indexOf(theme) + 1) % order.length])
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-1 border-b border-line bg-surface px-4">
      <button
        onClick={() => setLang(lang === 'es' ? 'en' : 'es')}
        className="rounded-md px-2.5 py-1.5 text-[13px] font-medium text-tx-2 hover:bg-surface-2"
      >
        {lang.toUpperCase()}
      </button>

      <button
        onClick={cycleTheme}
        className="rounded-md p-2 text-tx-2 hover:bg-surface-2"
        title={theme}
      >
        <ThemeIcon className="h-[18px] w-[18px]" />
      </button>

      <button className="relative rounded-md p-2 text-tx-2 hover:bg-surface-2">
        <Bell className="h-[18px] w-[18px]" />
        <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-pill bg-accent" />
      </button>

      <div className="relative ml-1">
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="flex items-center gap-2 rounded-lg p-1 hover:bg-surface-2"
        >
          <Avatar name={session?.name ?? '?'} size="sm" />
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 top-11 z-20 w-52 rounded-lg border border-line bg-surface p-1 shadow-lg animate-pop-in">
              <div className="border-b border-line-soft px-3 py-2">
                <p className="truncate text-sm font-medium text-tx">{session?.name}</p>
                <p className="truncate text-xs text-tx-3">{session?.email}</p>
              </div>
              <button
                onClick={() => {
                  logout()
                  navigate('/platform/login')
                }}
                className={cn(
                  'mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-[13px] text-tx-2',
                  'hover:bg-surface-2',
                )}
              >
                <LogOut className="h-4 w-4" />
                {t('platform.logout')}
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  )
}

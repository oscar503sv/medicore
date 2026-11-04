import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { useT } from '@/lib/i18n'

const CHECK_EVERY_MS = 5 * 60_000

/**
 * After a deploy, a tab that stays open keeps running the old code (navigation inside the
 * SPA never reloads it). Compare the running build with the published /version.json every
 * few minutes and whenever the tab regains focus, and offer a reload on mismatch.
 * Production builds only: dev has no version.json.
 */
export function UpdateNotice() {
  const t = useT()
  const [outdated, setOutdated] = useState(false)

  useEffect(() => {
    if (!import.meta.env.PROD || outdated) return
    const check = async () => {
      try {
        const res = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
        if (!res.ok) return
        const { build } = (await res.json()) as { build?: string }
        if (build && build !== __BUILD_ID__) setOutdated(true)
      } catch {
        // offline or mid-deploy: try again on the next tick
      }
    }
    const onVisible = () => document.visibilityState === 'visible' && check()
    const timer = window.setInterval(check, CHECK_EVERY_MS)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', check)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', check)
    }
  }, [outdated])

  if (!outdated) return null
  return (
    <div
      role="status"
      className="fixed bottom-6 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm shadow-lg animate-pop-in"
    >
      <RefreshCw className="h-4 w-4 text-accent" />
      <span className="text-tx">{t('app.update_available')}</span>
      <Button size="sm" onClick={() => window.location.reload()}>
        {t('app.update_reload')}
      </Button>
    </div>
  )
}

import { ShieldAlert } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { impersonationApi } from '@/api/platform'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppLayout() {
  const t = useT()
  const session = useAuthStore((s) => s.session)
  const logout = useAuthStore((s) => s.logout)

  // Record support.access.ended before tearing down the session. Best-effort: if the call
  // fails (expired token, network), we still leave. A hard redirect re-bootstraps from the
  // persisted platform session and avoids the SPA redirect race that would otherwise bounce
  // us to the tenant login the moment the tenant session is cleared.
  const exitSupport = async () => {
    try {
      await impersonationApi.end()
    } catch {
      // ignore — leaving the session is more important than the audit ping
    }
    logout()
    window.location.assign('/platform/clinics')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        {session?.impersonating && (
          <div className="flex items-center justify-center gap-3 bg-warn px-4 py-1.5 text-[13px] font-medium text-white">
            <ShieldAlert className="h-4 w-4" />
            {t('platform.impersonation_banner')}
            <button
              onClick={exitSupport}
              className="rounded-md bg-black/20 px-2 py-0.5 hover:bg-black/30"
            >
              {t('platform.impersonation_exit')}
            </button>
          </div>
        )}
        <Topbar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

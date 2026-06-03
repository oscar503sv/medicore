import { ShieldAlert } from 'lucide-react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppLayout() {
  const t = useT()
  const navigate = useNavigate()
  const session = useAuthStore((s) => s.session)
  const logout = useAuthStore((s) => s.logout)

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        {session?.impersonating && (
          <div className="flex items-center justify-center gap-3 bg-warn px-4 py-1.5 text-[13px] font-medium text-white">
            <ShieldAlert className="h-4 w-4" />
            {t('platform.impersonation_banner')}
            <button
              onClick={() => {
                logout()
                navigate('/platform/clinics')
              }}
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

import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'

export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useAuthStore((s) => s.session)
  const location = useLocation()
  if (!session) return <Navigate to="/login" replace />
  // Users created with a temporary password must set a new one before using the app.
  if (session.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />
  }
  return <>{children}</>
}

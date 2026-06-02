import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { usePlatformAuthStore } from '@/stores/platformAuth'

export function RequirePlatformAuth({ children }: { children: ReactNode }) {
  const session = usePlatformAuthStore((s) => s.session)
  if (!session) return <Navigate to="/platform/login" replace />
  return <>{children}</>
}

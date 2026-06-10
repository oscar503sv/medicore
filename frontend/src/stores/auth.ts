import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Permission, Role, Session } from '@/types'

interface AuthState {
  session: Session | null
  setSession: (session: Session) => void
  clearMustChangePassword: () => void
  logout: () => void
  hasRole: (...roles: Role[]) => boolean
  /** True if the session holds at least one of the given permissions. */
  can: (...permissions: Permission[]) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      session: null,
      setSession: (session) => set({ session }),
      clearMustChangePassword: () => {
        const s = get().session
        if (s) set({ session: { ...s, must_change_password: false } })
      },
      logout: () => set({ session: null }),
      hasRole: (...roles) => {
        const role = get().session?.role
        return role ? roles.includes(role) : false
      },
      can: (...permissions) => {
        const granted = get().session?.permissions
        return granted ? permissions.some((p) => granted.includes(p)) : false
      },
    }),
    {
      name: 'medicore-auth',
      // v1: sessions now carry `permissions`; drop older persisted sessions so the
      // user re-logs once and gets a complete session from the backend.
      version: 1,
      migrate: () => ({ session: null }),
    },
  ),
)

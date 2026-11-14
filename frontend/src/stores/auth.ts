import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { MyProfile, Permission, Role, Session } from '@/types'

// Plain fetch (not the axios instance — client.ts imports this store) to clear the
// httpOnly session cookie server-side; JS cannot delete it. Fire-and-forget.
export function serverLogout(path: string) {
  const base = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  void fetch(`${base}${path}`, { method: 'POST', credentials: 'include' }).catch(() => {})
}

interface AuthState {
  session: Session | null
  setSession: (session: Session) => void
  /** Refresh the server-owned fields of the current session from the user's profile. */
  syncProfile: (profile: MyProfile) => void
  clearMustChangePassword: () => void
  requirePasswordChange: () => void
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
      syncProfile: (profile) => {
        const s = get().session
        if (!s) return
        set({
          session: {
            ...s,
            name: profile.name,
            role: profile.role,
            sex: profile.sex,
            permissions: profile.permissions,
            must_change_password: profile.must_change_password,
            tenant_name: profile.tenant_name,
            timezone: profile.timezone,
          },
        })
      },
      clearMustChangePassword: () => {
        const s = get().session
        if (s) set({ session: { ...s, must_change_password: false } })
      },
      requirePasswordChange: () => {
        const s = get().session
        if (s) set({ session: { ...s, must_change_password: true } })
      },
      logout: () => {
        serverLogout('/auth/logout')
        set({ session: null })
      },
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
      // v2: the token moved to an httpOnly cookie; purge older persisted sessions
      // (which still contain it) so the user re-logs once.
      version: 2,
      migrate: () => ({ session: null }),
    },
  ),
)

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Role, Session } from '@/types'

interface AuthState {
  session: Session | null
  setSession: (session: Session) => void
  logout: () => void
  hasRole: (...roles: Role[]) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      session: null,
      setSession: (session) => set({ session }),
      logout: () => set({ session: null }),
      hasRole: (...roles) => {
        const role = get().session?.role
        return role ? roles.includes(role) : false
      },
    }),
    { name: 'medicore-auth' },
  ),
)

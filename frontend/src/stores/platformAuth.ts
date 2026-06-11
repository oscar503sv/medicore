import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { serverLogout } from '@/stores/auth'
import type { PlatformSession } from '@/types'

interface PlatformAuthState {
  session: PlatformSession | null
  setSession: (session: PlatformSession) => void
  logout: () => void
}

export const usePlatformAuthStore = create<PlatformAuthState>()(
  persist(
    (set) => ({
      session: null,
      setSession: (session) => set({ session }),
      logout: () => {
        serverLogout('/platform/logout')
        set({ session: null })
      },
    }),
    {
      name: 'medicore-platform',
      // v1: the token moved to an httpOnly cookie; purge older persisted sessions.
      version: 1,
      migrate: () => ({ session: null }),
    },
  ),
)

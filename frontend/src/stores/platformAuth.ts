import { create } from 'zustand'
import { persist } from 'zustand/middleware'
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
      logout: () => set({ session: null }),
    }),
    { name: 'medicore-platform' },
  ),
)

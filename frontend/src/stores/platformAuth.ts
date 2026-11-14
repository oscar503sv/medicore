import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { serverLogout } from '@/stores/auth'
import type { PlatformSession } from '@/types'

interface PlatformAuthState {
  session: PlatformSession | null
  /** Error code explaining why the console session ended, shown on the login page. */
  notice: string | null
  setSession: (session: PlatformSession) => void
  logout: () => void
  /** The server already ended the session: drop it locally and remember why. */
  expire: (code?: string) => void
  clearNotice: () => void
}

export const usePlatformAuthStore = create<PlatformAuthState>()(
  persist(
    (set) => ({
      session: null,
      notice: null,
      setSession: (session) => set({ session, notice: null }),
      logout: () => {
        serverLogout('/platform/logout')
        set({ session: null })
      },
      expire: (code) => set({ session: null, notice: code ?? 'auth.session_expired' }),
      clearNotice: () => set({ notice: null }),
    }),
    {
      name: 'medicore-platform',
      // v1: the token moved to an httpOnly cookie; purge older persisted sessions.
      version: 1,
      migrate: () => ({ session: null }),
      partialize: (state) => ({ session: state.session }),
    },
  ),
)

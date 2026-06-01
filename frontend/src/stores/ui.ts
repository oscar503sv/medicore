import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'
export type Lang = 'es' | 'en'

interface UIState {
  theme: Theme
  lang: Lang
  sidebarCollapsed: boolean
  setTheme: (theme: Theme) => void
  setLang: (lang: Lang) => void
  toggleSidebar: () => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: 'system',
      lang: 'es',
      sidebarCollapsed: false,
      setTheme: (theme) => set({ theme }),
      setLang: (lang) => set({ lang }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: 'medicore-ui' },
  ),
)

/** Resolve the effective theme (light/dark) and apply it to <html data-theme>. */
export function applyTheme(theme: Theme) {
  const isDark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
}

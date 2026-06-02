import { api } from './client'
import type { Session } from '@/types'

export interface LoginPayload {
  slug: string
  email: string
  password: string
}

export const authApi = {
  login: (payload: LoginPayload) =>
    api.post<Session>('/auth/login', payload).then((r) => r.data),

  switchTheme: (theme: string) => api.post('/auth/theme', { theme }),

  switchLocale: (language: string) => api.post('/auth/locale', { language }),

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
}

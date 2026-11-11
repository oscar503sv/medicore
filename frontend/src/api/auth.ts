import { api } from './client'
import type { AuthSessionInfo, MyProfile, Session, SubscriptionNotice } from '@/types'

export interface LoginPayload {
  slug: string
  email: string
  password: string
}

export interface OnboardingStep {
  key: string
  done: boolean
  optional: boolean
}

export interface Onboarding {
  welcome_seen: boolean
  dismissed: boolean
  /** Empty for roles without a checklist, and once dismissed. */
  steps: OnboardingStep[]
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

  getMyProfile: () => api.get<MyProfile>('/auth/me').then((r) => r.data),

  updateMyProfile: (payload: { name?: string; phone?: string | null; bio?: string | null }) =>
    api.patch<MyProfile>('/auth/me', payload).then((r) => r.data),

  listSessions: () =>
    api.get<{ items: AuthSessionInfo[] }>('/auth/me/sessions').then((r) => r.data.items),

  revokeSession: (sessionId: string) => api.delete(`/auth/me/sessions/${sessionId}`),

  onboarding: () => api.get<Onboarding>('/auth/me/onboarding').then((r) => r.data),

  subscriptionNotice: () =>
    api.get<SubscriptionNotice>('/auth/me/subscription').then((r) => r.data),

  updateOnboarding: (payload: { welcome_seen?: boolean; dismissed?: boolean }) =>
    api.patch('/auth/me/onboarding', payload),
}

import { api } from './client'
import type { AuthSessionInfo, PaginatedResponse, User } from '@/types'

export const usersApi = {
  list: (params: { role?: string; status?: string; offset?: number; limit?: number } = {}) =>
    api.get<PaginatedResponse<User>>('/users', { params }).then((r) => r.data),

  invite: (payload: {
    name: string
    email: string
    role: string
    password: string
    sex?: string | null
    phone?: string | null
    specialty?: string | null
  }) => api.post<User>('/users', payload).then((r) => r.data),

  update: (
    id: string,
    payload: {
      name?: string
      role?: string
      sex?: string | null
      phone?: string | null
      specialty?: string | null
    },
  ) => api.patch<User>(`/users/${id}`, payload).then((r) => r.data),

  updateRole: (id: string, role: string) =>
    api.put<User>(`/users/${id}/role`, { role }).then((r) => r.data),

  suspend: (id: string) => api.post<User>(`/users/${id}/suspend`).then((r) => r.data),

  reactivate: (id: string) => api.post<User>(`/users/${id}/reactivate`).then((r) => r.data),

  resetPassword: (id: string, password: string) =>
    api.post<User>(`/users/${id}/reset-password`, { password }).then((r) => r.data),

  listSessions: (id: string) =>
    api.get<{ items: AuthSessionInfo[] }>(`/users/${id}/sessions`).then((r) => r.data.items),

  revokeSession: (id: string, sessionId: string) =>
    api.delete(`/users/${id}/sessions/${sessionId}`),

  revokeAllSessions: (id: string) => api.delete(`/users/${id}/sessions`),
}

import { api } from './client'
import type { PaginatedResponse, User } from '@/types'

export const usersApi = {
  list: (params: { role?: string; status?: string; offset?: number; limit?: number } = {}) =>
    api.get<PaginatedResponse<User>>('/users', { params }).then((r) => r.data),

  invite: (payload: { name: string; email: string; role: string; specialty?: string | null }) =>
    api.post<User>('/users', payload).then((r) => r.data),

  updateRole: (id: string, role: string) =>
    api.put<User>(`/users/${id}/role`, { role }).then((r) => r.data),

  suspend: (id: string) => api.post<User>(`/users/${id}/suspend`).then((r) => r.data),
}

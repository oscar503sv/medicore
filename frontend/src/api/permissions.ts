import { api } from './client'
import type { Permission, PermissionsMatrix, Role } from '@/types'

export const permissionsApi = {
  getMatrix: () => api.get<PermissionsMatrix>('/permissions').then((r) => r.data),

  updateRole: (role: Role, permissions: Permission[]) =>
    api
      .put<PermissionsMatrix>(`/permissions/roles/${role}`, { permissions })
      .then((r) => r.data),

  resetRole: (role: Role) =>
    api.delete<PermissionsMatrix>(`/permissions/roles/${role}`).then((r) => r.data),
}

import { api } from './client'
import type { AppNotification } from '@/types'

export type NotificationCategory = 'appointment' | 'record' | 'document' | 'user'

export interface NotificationList {
  items: AppNotification[]
  unread_count: number
}

export const notificationsApi = {
  list: (
    params: {
      unread_only?: boolean
      category?: NotificationCategory
      offset?: number
      limit?: number
    } = {},
  ) =>
    api.get<NotificationList>('/notifications', { params }).then((r) => r.data),

  unreadCount: () =>
    api
      .get<{ unread_count: number }>('/notifications/unread-count')
      .then((r) => r.data.unread_count),

  markRead: (id: string) =>
    api.post<AppNotification>(`/notifications/${id}/read`).then((r) => r.data),

  markAllRead: () =>
    api.post<{ marked: number }>('/notifications/read-all').then((r) => r.data.marked),
}

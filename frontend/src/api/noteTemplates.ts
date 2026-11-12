import { api } from './client'
import type { NoteCatalog, NoteSettings } from '@/types'

export const noteTemplatesApi = {
  catalog: () => api.get<NoteCatalog>('/note-templates').then((r) => r.data),

  updateSettings: (settings: NoteSettings) =>
    api.put<NoteCatalog>('/note-templates/settings', settings).then((r) => r.data),

  setFavourite: (template: string | null) =>
    api.put<NoteCatalog>('/note-templates/favourite', { template }).then((r) => r.data),
}

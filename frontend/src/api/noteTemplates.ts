import { api } from './client'
import type { NoteCatalog, NoteSettings, SectionInput } from '@/types'

export const noteTemplatesApi = {
  catalog: () => api.get<NoteCatalog>('/note-templates').then((r) => r.data),

  updateSettings: (settings: NoteSettings) =>
    api.put<NoteCatalog>('/note-templates/settings', settings).then((r) => r.data),

  setFavourite: (template: string | null) =>
    api.put<NoteCatalog>('/note-templates/favourite', { template }).then((r) => r.data),

  create: (payload: { name: string; sections: SectionInput[] }) =>
    api.post<NoteCatalog>('/note-templates', payload).then((r) => r.data),

  update: (id: string, payload: { name: string; sections: SectionInput[] }) =>
    api.put<NoteCatalog>(`/note-templates/${id}`, payload).then((r) => r.data),

  archive: (id: string) => api.delete<NoteCatalog>(`/note-templates/${id}`).then((r) => r.data),
}

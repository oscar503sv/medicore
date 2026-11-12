// Clinical note helpers: names of built-in templates and sections are translated by key;
// custom clinic templates show the titles they were written with.
import type { NoteRole } from '@/types'

type T = (key: string) => string

export const SYSTEM_TEMPLATES = ['soap', 'psoap', 'history', 'evolution', 'narrative']

export const isSystemTemplate = (key: string) => SYSTEM_TEMPLATES.includes(key)

export function templateName(t: T, key: string, name: string): string {
  return isSystemTemplate(key) ? t(`note.template.${key}`) : name
}

export function sectionTitle(t: T, template: string, section: { key: string; title: string }) {
  return isSystemTemplate(template) ? t(`note.section.${section.key}`) : section.title
}

export function sectionHint(t: T, template: string, key: string): string | null {
  return isSystemTemplate(template) ? t(`note.hint.${key}`) : null
}

const ROLE_LETTERS: Record<NoteRole, string> = {
  problems: 'P',
  subjective: 'S',
  history: 'H',
  objective: 'O',
  assessment: 'A',
  plan: 'P',
  free: 'N',
}

export const roleLetter = (role: NoteRole) => ROLE_LETTERS[role]

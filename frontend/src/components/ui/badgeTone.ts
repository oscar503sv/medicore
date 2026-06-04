export type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info' | 'accent'

/** Text-colour class per tone (for icons/labels outside the Badge pill). */
export const TONE_TEXT: Record<Tone, string> = {
  neutral: 'text-tx-3',
  ok: 'text-ok',
  warn: 'text-warn',
  danger: 'text-danger',
  info: 'text-info',
  accent: 'text-accent',
}

const STATUS_TONE: Record<string, Tone> = {
  scheduled: 'info',
  confirmed: 'accent',
  in_progress: 'warn',
  completed: 'ok',
  cancelled: 'danger',
  no_show: 'danger',
  active: 'ok',
  pending: 'warn',
  suspended: 'danger',
  signed: 'ok',
  amended: 'info',
}

export function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? 'neutral'
}

const TYPE_TONE: Record<string, Tone> = {
  consult: 'info',
  follow_up: 'accent',
  check_up: 'ok',
  procedure: 'warn',
  emergency: 'danger',
}

export function typeTone(type: string): Tone {
  return TYPE_TONE[type] ?? 'neutral'
}

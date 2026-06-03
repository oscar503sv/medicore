export type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info' | 'accent'

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

import type {
  Procedure,
  ProcedurePerformer,
  ProcedureStatus,
  ProcedureType,
} from '@/api/procedures'
import type { Tone } from '@/components/ui/badgeTone'
import { useAuthStore } from '@/stores/auth'

export const STATUS_TONE: Record<ProcedureStatus, Tone> = {
  pending: 'warn',
  in_progress: 'info',
  completed: 'ok',
  cancelled: 'neutral',
}

export const isOpen = (p: Procedure) => p.status === 'pending' || p.status === 'in_progress'

/**
 * Who may perform what, mirroring the backend: a doctor performs any procedure; nursing only
 * the "doctor or nurse" ones; both also need procedures.perform.
 */
export function usePerformer() {
  const canPerform = useAuthStore((s) => s.can('procedures.perform'))
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const isNurse = useAuthStore((s) => s.hasRole('nurse'))
  const can = (performer: ProcedurePerformer) =>
    canPerform && (isDoctor || (isNurse && performer === 'doctor_or_nurse'))
  return {
    canPerform,
    isDoctor,
    can,
    /** Active catalog types this user may perform. */
    types: (all: ProcedureType[]) => all.filter((k) => k.active && can(k.performer)),
  }
}

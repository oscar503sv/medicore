import { useEffect, useState } from 'react'
import type { ApplicationOrder, ApplicationOrderStatus } from '@/api/applications'
import type { Tone } from '@/components/ui/badgeTone'

type T = (key: string) => string

interface Plan {
  doses_total: number
  interval_hours: number | null
}

/** "Dosis única" / "3 dosis cada 24 h". */
export function planLabel(t: T, plan: Plan): string {
  if (plan.doses_total <= 1) return t('apl.plan_single')
  return t('apl.plan_multi')
    .replace('{n}', String(plan.doses_total))
    .replace('{h}', String(plan.interval_hours ?? ''))
}

/** "Indicó Dr. Marco Vidal" / "Dra. Ana Ramos · JVPM 4321". */
export function originLabel(t: T, order: ApplicationOrder): string {
  if (order.source === 'external') {
    return t('apl.external_by')
      .replace('{name}', order.external_prescriber ?? '—')
      .replace('{jvpm}', order.external_jvpm ?? '—')
  }
  return t('apl.ordered_by').replace('{name}', order.ordered_by_name ?? '—')
}

export const ORDER_TONE: Record<ApplicationOrderStatus, Tone> = {
  pending: 'warn',
  in_progress: 'info',
  completed: 'ok',
  cancelled: 'neutral',
}

/** Minutes left until `until` (an ISO instant), re-rendering every 15 s. Negative = overdue. */
export function useMinutesLeft(until: string | null): number | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!until) return
    const id = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(id)
  }, [until])
  if (!until) return null
  return Math.ceil((Date.parse(until) - now) / 60_000)
}

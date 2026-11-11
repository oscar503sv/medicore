import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Clock, Lock } from 'lucide-react'
import { authApi } from '@/api/auth'
import { cn } from '@/lib/cn'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

// How many days ahead admins are reminded that the trial or the paid period ends.
const TRIAL_WARNING_DAYS = 3
const RENEWAL_WARNING_DAYS = 5

/** App-wide banner for the clinic's subscription: read-only (everyone), grace period and
 * upcoming end of trial / paid period (admins, who can do something about it). */
export function SubscriptionBanner() {
  const t = useT()
  const isAdmin = useAuthStore((s) => s.can('organization.view'))
  const { data: n } = useQuery({
    queryKey: ['subscription-notice'],
    queryFn: authApi.subscriptionNotice,
    staleTime: 5 * 60_000,
  })
  if (!n) return null

  const date = fmtDate(n.period_end)
  let tone: 'danger' | 'warn' | 'info' | null = null
  let text = ''
  if (n.status === 'read_only') {
    tone = 'danger'
    text = t(isAdmin ? 'sub.banner_read_only_admin' : 'sub.banner_read_only_staff')
  } else if (!isAdmin) {
    return null
  } else if (n.status === 'grace') {
    tone = 'warn'
    text = t('sub.banner_grace').replace('{until}', fmtDate(n.grace_until))
  } else if (n.status === 'trial' && n.days_left !== null && n.days_left <= TRIAL_WARNING_DAYS) {
    tone = 'info'
    text = t('sub.banner_trial')
  } else if (n.status === 'active' && n.days_left !== null && n.days_left <= RENEWAL_WARNING_DAYS) {
    tone = 'info'
    text = t('sub.banner_expiring')
  }
  if (!tone) return null

  const Icon = tone === 'danger' ? Lock : tone === 'warn' ? AlertTriangle : Clock
  return (
    <div
      role="status"
      className={cn(
        'flex items-center justify-center gap-2 px-4 py-1.5 text-center text-[13px] font-medium text-white',
        tone === 'danger' && 'bg-danger',
        tone === 'warn' && 'bg-warn',
        tone === 'info' && 'bg-info',
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {text.replace('{date}', date)}
    </div>
  )
}

import { Badge } from '@/components/ui/Badge'
import { useT } from '@/lib/i18n'
import { SUBSCRIPTION_TONE } from '@/lib/subscriptions'
import type { SubscriptionStatus } from '@/types'

export function SubscriptionBadge({ status }: { status: SubscriptionStatus }) {
  const t = useT()
  return <Badge tone={SUBSCRIPTION_TONE[status]}>{t(`sub.status.${status}`)}</Badge>
}

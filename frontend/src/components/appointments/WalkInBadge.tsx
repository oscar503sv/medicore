import { Badge } from '@/components/ui/Badge'
import { useT } from '@/lib/i18n'

export function WalkInBadge() {
  const t = useT()
  return <Badge tone="danger">{t('appt.walk_in_badge')}</Badge>
}

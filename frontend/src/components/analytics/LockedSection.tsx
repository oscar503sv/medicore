import { Lock } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { useT } from '@/lib/i18n'

/** What a higher analytics tier adds, in place of the sections the clinic doesn't have. */
export function LockedSection({ tier }: { tier: 'clinic' | 'operations' }) {
  const t = useT()
  return (
    <Card className="flex items-start gap-4 border-dashed p-5">
      <div className="rounded-lg bg-surface-2 p-2">
        <Lock className="h-4 w-4 text-tx-3" />
      </div>
      <div>
        <p className="text-sm font-semibold text-tx">{t(`an.locked_${tier}_title`)}</p>
        <p className="mt-1 text-[13px] text-tx-3">{t(`an.locked_${tier}`)}</p>
        <p className="mt-1 text-xs text-tx-4">{t('an.locked_contact')}</p>
      </div>
    </Card>
  )
}

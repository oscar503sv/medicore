import { Construction } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { useT } from '@/lib/i18n'

/** Placeholder for clinical modules not yet implemented (applications, procedures, vaccination). */
export function ComingSoonPage() {
  const t = useT()
  return (
    <div className="space-y-5 p-8">
      <Card>
        <EmptyState
          icon={Construction}
          title={t('coming_soon.title')}
          description={t('coming_soon.desc')}
        />
      </Card>
    </div>
  )
}

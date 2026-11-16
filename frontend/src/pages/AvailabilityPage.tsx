import { myAvailability } from '@/api/availability'
import { AvailabilityEditor } from '@/components/availability/AvailabilityEditor'
import { PageHeader } from '@/components/PageHeader'
import { useT } from '@/lib/i18n'

export function AvailabilityPage() {
  const t = useT()
  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('avail.title')} />
      <AvailabilityEditor scope={myAvailability} scopeKey="me" />
    </div>
  )
}

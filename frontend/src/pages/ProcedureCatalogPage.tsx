import { Navigate } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { ProcedureCatalog } from '@/components/procedures/ProcedureCatalog'
import { Card } from '@/components/ui/Card'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

/** Management shortcut to the clinic's procedure catalog (also a tab on /procedures). */
export function ProcedureCatalogPage() {
  const t = useT()
  const canCatalog = useAuthStore((s) => s.can('procedures.catalog'))
  if (!canCatalog) return <Navigate to="/procedures" replace />
  return (
    <div className="space-y-5 p-8">
      <PageHeader eyebrow={t('prc.page_title')} title={t('nav.procedure_catalog')} />
      <Card>
        <ProcedureCatalog />
      </Card>
    </div>
  )
}

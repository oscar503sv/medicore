import { FileSignature, FlaskConical } from 'lucide-react'
import type { Procedure } from '@/api/procedures'
import { useT } from '@/lib/i18n'

/** Procedure name, indication and the rule badges (consent, specimen). */
export function ProcedureCell({ p }: { p: Procedure }) {
  const t = useT()
  return (
    <div>
      <p className="flex items-center gap-1.5 font-medium text-tx">
        {p.type_name}
        {p.requires_consent && (
          <span title={t('prc.consent_badge')}>
            <FileSignature className="h-3.5 w-3.5 text-tx-3" />
          </span>
        )}
        {p.takes_specimen && (
          <span title={t('prc.specimen_badge')}>
            <FlaskConical className="h-3.5 w-3.5 text-tx-3" />
          </span>
        )}
      </p>
      <p className="max-w-xs truncate text-xs text-tx-3" title={p.indication}>
        {p.indication}
      </p>
    </div>
  )
}

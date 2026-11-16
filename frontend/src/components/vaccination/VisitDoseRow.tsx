import { Trash2 } from 'lucide-react'
import type { DoseState, VaccinationCatalog } from '@/api/vaccinations'
import { useT } from '@/lib/i18n'
import { openDoses } from '@/lib/vaccination'
import { AdministrationFields, VaccineDoseSelects } from './DoseFields'
import type { DoseRow } from './useVaccinationVisit'

/** One dose of a visit: always given here, so the lot is required. */
export function VisitDoseRow({
  index,
  row,
  catalog,
  states,
  canRemove,
  onChange,
  onVaccine,
  onRemove,
}: {
  index: number
  row: DoseRow
  catalog: VaccinationCatalog
  states: DoseState[]
  canRemove: boolean
  onChange: (patch: Partial<DoseRow>) => void
  onVaccine: (code: string) => void
  onRemove: () => void
}) {
  const t = useT()
  return (
    <fieldset className="space-y-3 rounded-lg border border-line p-3">
      <legend className="flex items-center gap-2 px-1 text-[13px] font-medium text-tx-2">
        {t('vax.visit_dose_n').replace('{n}', String(index + 1))}
        {canRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={t('vax.visit_remove_dose').replace('{n}', String(index + 1))}
            className="rounded p-1 text-tx-4 hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </legend>
      <VaccineDoseSelects
        catalog={catalog}
        vaccine={row.vaccine}
        doseKey={row.doseKey}
        doses={openDoses(catalog, states, row.vaccine)}
        onVaccine={onVaccine}
        onDose={(doseKey) => onChange({ doseKey })}
      />
      <AdministrationFields
        lot={row.lot}
        route={row.route}
        site={row.site}
        defaultRoute={catalog.vaccines.find((v) => v.code === row.vaccine)?.route}
        onLot={(lot) => onChange({ lot })}
        onRoute={(route) => onChange({ route })}
        onSite={(site) => onChange({ site })}
      />
    </fieldset>
  )
}

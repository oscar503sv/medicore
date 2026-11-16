import type {
  InjectionSite,
  ScheduledDose,
  VaccinationCatalog,
  VaccineRoute,
} from '@/api/vaccinations'
import { Input, Select } from '@/components/ui/Input'
import { useT } from '@/lib/i18n'
import { ageLabel, doseLabel, vaccineDiseases, vaccineName } from '@/lib/vaccination'

const ROUTES: VaccineRoute[] = ['im', 'sc', 'id', 'oral']
const SITES: InjectionSite[] = ['left_arm', 'right_arm', 'left_thigh', 'right_thigh', 'mouth']

/** Vaccine and dose pickers; `doses` are the ones still open for the patient. */
export function VaccineDoseSelects({
  catalog,
  vaccine,
  doseKey,
  doses,
  onVaccine,
  onDose,
}: {
  catalog: VaccinationCatalog
  vaccine: string
  doseKey: string
  doses: ScheduledDose[]
  onVaccine: (code: string) => void
  onDose: (key: string) => void
}) {
  const t = useT()
  const diseases = vaccineDiseases(t, vaccine)
  return (
    <div className="grid gap-4 sm:grid-cols-[1.4fr_1fr]">
      <div>
        <Select
          label={t('vax.vaccine')}
          value={vaccine}
          onChange={(e) => onVaccine(e.target.value)}
        >
          {[
            ...catalog.vaccines.filter((v) => v.in_schedule),
            ...catalog.vaccines.filter((v) => !v.in_schedule),
          ].map((v) => (
            <option key={v.code} value={v.code}>
              {v.in_schedule
                ? vaccineName(t, v.code)
                : `${vaccineName(t, v.code)} · ${t('vax.out_of_scheme')}`}
            </option>
          ))}
        </Select>
        {diseases && <p className="mt-1 text-xs text-tx-3">{diseases}</p>}
      </div>
      <Select label={t('vax.dose')} value={doseKey} onChange={(e) => onDose(e.target.value)}>
        {doses.map((d) => (
          <option key={d.key} value={d.key}>
            {`${doseLabel(t, d)} · ${ageLabel(t, d.age_months)}`}
          </option>
        ))}
        <option value="">{t('vax.dose_none')}</option>
      </Select>
    </div>
  )
}

/** Lot (required: the dose is given here), route and site. */
export function AdministrationFields({
  lot,
  route,
  site,
  defaultRoute,
  onLot,
  onRoute,
  onSite,
}: {
  lot: string
  route: VaccineRoute | ''
  site: InjectionSite | ''
  /** The vaccine's usual route, shown until another is picked. */
  defaultRoute: VaccineRoute | undefined
  onLot: (lot: string) => void
  onRoute: (route: VaccineRoute) => void
  onSite: (site: InjectionSite | '') => void
}) {
  const t = useT()
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Input
        label={t('vax.lot')}
        value={lot}
        placeholder={t('vax.lot_ph')}
        onChange={(e) => onLot(e.target.value)}
        className="font-mono"
        required
      />
      <Select
        label={t('vax.route')}
        value={route || defaultRoute || ''}
        onChange={(e) => onRoute(e.target.value as VaccineRoute)}
      >
        {ROUTES.map((r) => (
          <option key={r} value={r}>
            {t(`vax.route.${r}`)}
          </option>
        ))}
      </Select>
      <Select
        label={t('vax.site')}
        value={site}
        onChange={(e) => onSite(e.target.value as InjectionSite | '')}
      >
        <option value="">{t('vax.site_none')}</option>
        {SITES.map((s) => (
          <option key={s} value={s}>
            {t(`vax.site.${s}`)}
          </option>
        ))}
      </Select>
    </div>
  )
}

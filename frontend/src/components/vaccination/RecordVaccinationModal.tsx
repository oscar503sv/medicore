import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, FileText } from 'lucide-react'
import { errorMessage } from '@/api/client'
import {
  vaccinationsApi,
  type DoseState,
  type InjectionSite,
  type VaccinationCatalog,
  type VaccinationOutcome,
  type VaccinationSource,
  type VaccineRoute,
} from '@/api/vaccinations'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Segmented } from '@/components/ui/Segmented'
import { toast } from '@/components/ui/Toast'
import { clinicToday } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { ageLabel, doseLabel, vaccineDiseases, vaccineName } from '@/lib/vaccination'

const ROUTES: VaccineRoute[] = ['im', 'sc', 'id', 'oral']
const SITES: InjectionSite[] = ['left_arm', 'right_arm', 'left_thigh', 'right_thigh', 'mouth']

export interface RecordPreset {
  vaccine?: string
  dose?: string
}

/**
 * Record a dose for a patient: given here (lot required), copied from the vaccination card
 * (given elsewhere), refused or contraindicated. `states` limits the dose list to the doses
 * that apply to this patient and are not yet settled.
 */
export function RecordVaccinationModal({
  patientId,
  catalog,
  states,
  preset,
  onClose,
}: {
  patientId: string
  catalog: VaccinationCatalog
  states: DoseState[]
  /** null = closed. */
  preset: RecordPreset | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const open = preset !== null

  const [vaccine, setVaccine] = useState('')
  const [doseKey, setDoseKey] = useState('')
  const [outcome, setOutcome] = useState<VaccinationOutcome>('administered')
  const [source, setSource] = useState<VaccinationSource>('clinic')
  const [date, setDate] = useState(clinicToday())
  const [lot, setLot] = useState('')
  const [route, setRoute] = useState<VaccineRoute | ''>('')
  const [site, setSite] = useState<InjectionSite | ''>('')
  const [notes, setNotes] = useState('')

  const stateByKey = useMemo(() => new Map(states.map((s) => [s.key, s])), [states])
  // Doses of the chosen vaccine that apply to this patient and can still be recorded
  // (periodic doses repeat, so they are always offered).
  const doses = useMemo(
    () =>
      catalog.doses.filter((d) => {
        if (d.vaccine !== vaccine) return false
        const st = stateByKey.get(d.key)
        if (!st) return false // other sex
        return d.repeat_months != null || st.status !== 'administered'
      }),
    [catalog.doses, vaccine, stateByKey],
  )
  const vaccineInfo = catalog.vaccines.find((v) => v.code === vaccine)

  useEffect(() => {
    if (!preset) return
    // Default to the most pressing dose: overdue, then due, then due soon.
    const pressing = (['overdue', 'due', 'due_soon'] as const)
      .map((st) => states.find((s) => s.status === st))
      .find(Boolean)
    const pressingDose = pressing && catalog.doses.find((d) => d.key === pressing.key)
    setVaccine(preset.vaccine ?? pressingDose?.vaccine ?? catalog.vaccines[0]?.code ?? '')
    setDoseKey(preset.dose ?? pressingDose?.key ?? '')
    setOutcome('administered')
    setSource('clinic')
    setDate(clinicToday())
    setLot('')
    setRoute('')
    setSite('')
    setNotes('')
    // Reset only when the modal opens: a background refetch of the card must not wipe
    // what the user is typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset])

  // Changing vaccine resets the dose to its first open one, and the route to its default.
  const pickVaccine = (code: string) => {
    setVaccine(code)
    const firstOpen = catalog.doses.find((d) => {
      const st = stateByKey.get(d.key)
      return d.vaccine === code && st && (d.repeat_months != null || st.status !== 'administered')
    })
    setDoseKey(firstOpen?.key ?? '')
    setRoute('')
  }
  useEffect(() => {
    if (open && vaccine && !doseKey && doses.length && !preset?.dose) setDoseKey(doses[0].key)
  }, [open, vaccine, doseKey, doses, preset])

  const hereGiven = outcome === 'administered' && source === 'clinic'

  const save = useMutation({
    mutationFn: () =>
      vaccinationsApi.record(patientId, {
        vaccine_code: vaccine,
        dose_key: doseKey || null,
        outcome,
        occurred_on: date,
        source,
        lot: outcome === 'administered' ? lot.trim() || null : null,
        route: hereGiven ? route || null : null,
        site: hereGiven ? site || null : null,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vaccination-card', patientId] })
      qc.invalidateQueries({ queryKey: ['vaccination-worklist'] })
      toast(t('vax.record_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const inScheme = catalog.vaccines.filter((v) => v.in_schedule)
  const extra = catalog.vaccines.filter((v) => !v.in_schedule)
  const diseases = vaccineDiseases(t, vaccine)

  return (
    <Modal open={open} onClose={onClose} title={t('vax.record_title')} width="max-w-xl">
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <div className="grid gap-4 sm:grid-cols-[1.4fr_1fr]">
          <div>
            <Select
              label={t('vax.vaccine')}
              value={vaccine}
              onChange={(e) => pickVaccine(e.target.value)}
            >
              {inScheme.map((v) => (
                <option key={v.code} value={v.code}>
                  {vaccineName(t, v.code)}
                </option>
              ))}
              {extra.map((v) => (
                <option key={v.code} value={v.code}>
                  {`${vaccineName(t, v.code)} · ${t('vax.out_of_scheme')}`}
                </option>
              ))}
            </Select>
            {diseases && <p className="mt-1 text-xs text-tx-3">{diseases}</p>}
          </div>
          <Select
            label={t('vax.dose')}
            value={doseKey}
            onChange={(e) => setDoseKey(e.target.value)}
          >
            {doses.map((d) => (
              <option key={d.key} value={d.key}>
                {`${doseLabel(t, d)} · ${ageLabel(t, d.age_months)}`}
              </option>
            ))}
            <option value="">{t('vax.dose_none')}</option>
          </Select>
        </div>

        <div>
          <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{t('vax.outcome')}</span>
          <Segmented<VaccinationOutcome>
            value={outcome}
            onChange={setOutcome}
            options={(['administered', 'refused', 'contraindicated'] as const).map((o) => ({
              value: o,
              label: t(`vax.outcome.${o}`),
            }))}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
          <Input
            type="date"
            label={t('vax.date')}
            value={date}
            max={clinicToday()}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          {outcome === 'administered' && (
            <div>
              <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
                {t('vax.source')}
              </span>
              <Segmented<VaccinationSource>
                value={source}
                onChange={setSource}
                options={[
                  {
                    value: 'clinic',
                    label: (
                      <span className="inline-flex items-center gap-1.5">
                        <Building2 className="h-3.5 w-3.5" />
                        {t('vax.source.clinic')}
                      </span>
                    ),
                  },
                  {
                    value: 'external',
                    label: (
                      <span className="inline-flex items-center gap-1.5">
                        <FileText className="h-3.5 w-3.5" />
                        {t('vax.source.external')}
                      </span>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </div>

        {outcome === 'administered' && source === 'external' && (
          <p className="rounded-lg bg-surface-2 px-3 py-2 text-xs text-tx-3">
            {t('vax.external_hint')}
          </p>
        )}

        {hereGiven && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Input
              label={t('vax.lot')}
              value={lot}
              placeholder={t('vax.lot_ph')}
              onChange={(e) => setLot(e.target.value)}
              className="font-mono"
              required
            />
            <Select
              label={t('vax.route')}
              value={route || vaccineInfo?.route || ''}
              onChange={(e) => setRoute(e.target.value as VaccineRoute)}
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
              onChange={(e) => setSite(e.target.value as InjectionSite | '')}
            >
              <option value="">{t('vax.site_none')}</option>
              {SITES.map((s) => (
                <option key={s} value={s}>
                  {t(`vax.site.${s}`)}
                </option>
              ))}
            </Select>
          </div>
        )}

        {outcome === 'administered' && source === 'external' && (
          <Input
            label={t('vax.lot_optional')}
            value={lot}
            placeholder={t('vax.lot_ph')}
            onChange={(e) => setLot(e.target.value)}
            className="font-mono"
          />
        )}

        <Textarea
          label={t('vax.notes')}
          rows={2}
          value={notes}
          placeholder={t('vax.notes_ph')}
          onChange={(e) => setNotes(e.target.value)}
        />

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" variant="accent" loading={save.isPending} disabled={!vaccine}>
            {t('vax.record')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

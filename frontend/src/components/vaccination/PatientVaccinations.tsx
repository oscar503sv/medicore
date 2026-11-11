import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { addYears, differenceInMonths, format, parseISO } from 'date-fns'
import { Ban, Building2, ChevronDown, FileText, Plus, Printer, Syringe } from 'lucide-react'
import {
  vaccinationsApi,
  type DoseState,
  type ScheduledDose,
  type VaccinationRecord,
  type VaccineStage,
} from '@/api/vaccinations'
import { openPrint } from '@/api/printing'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Menu } from '@/components/ui/Menu'
import { PageLoader } from '@/components/ui/Spinner'
import { cn } from '@/lib/cn'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import {
  STATUS_TONE,
  ageLabel,
  doseLabel,
  isPending,
  vaccineDiseases,
  vaccineName,
} from '@/lib/vaccination'
import { useAuthStore } from '@/stores/auth'
import { RecordVaccinationModal, type RecordPreset } from './RecordVaccinationModal'
import { VoidVaccinationModal } from './VoidVaccinationModal'

const STAGES: VaccineStage[] = ['childhood', 'adolescence', 'adulthood', 'indicated']
/** Upcoming doses further away than this are folded with the not-applicable ones. */
const FAR_YEARS = 2

interface Row {
  dose: ScheduledDose
  state: DoseState
}

/** The patient's vaccination card: national scheme by stage, plus the record history. */
export function PatientVaccinations({
  patientId,
  birthDate,
  active,
}: {
  patientId: string
  birthDate: string
  /** Archived patients can't get new records. */
  active: boolean
}) {
  const t = useT()
  const canRecord = useAuthStore((s) => s.can('vaccinations.record')) && active
  const [preset, setPreset] = useState<RecordPreset | null>(null)
  const [voiding, setVoiding] = useState<VaccinationRecord | null>(null)
  const [showAll, setShowAll] = useState(false)

  const { data: catalog } = useQuery({
    queryKey: ['vaccination-catalog'],
    queryFn: vaccinationsApi.catalog,
    staleTime: Infinity,
  })
  const { data: card } = useQuery({
    queryKey: ['vaccination-card', patientId],
    queryFn: () => vaccinationsApi.card(patientId),
  })

  const { byStage, hidden, overdue, pending } = useMemo(() => {
    const byStage = new Map<VaccineStage, Row[]>()
    let hidden = 0
    let overdue = 0
    let pending = 0
    if (!catalog || !card) return { byStage, hidden, overdue, pending }
    const doses = new Map(catalog.doses.map((d) => [d.key, d]))
    const far = format(addYears(parseISO(card.today), FAR_YEARS), 'yyyy-MM-dd')
    const ageMonths = differenceInMonths(parseISO(card.today), parseISO(birthDate))
    for (const state of card.states) {
      const dose = doses.get(state.key)
      if (!dose) continue
      if (state.status === 'overdue') overdue++
      if (isPending(state.status)) pending++
      const folded =
        state.status === 'not_applicable' ||
        (state.status === 'upcoming' && !!state.due_on && state.due_on > far) ||
        // e.g. adult hepatitis B on a baby's card
        (state.status === 'indicated' && dose.age_months > ageMonths)
      if (folded) hidden++
      if (folded && !showAll) continue
      const list = byStage.get(dose.stage) ?? []
      list.push({ dose, state })
      byStage.set(dose.stage, list)
    }
    return { byStage, hidden, overdue, pending }
  }, [catalog, card, showAll, birthDate])

  if (!catalog || !card) return <PageLoader />

  return (
    <div className="space-y-5">
      {/* Summary strip */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-[13px] text-tx-3">
          <Syringe className="h-4 w-4" />
          {t('vax.scheme')}
        </div>
        <div className="flex gap-1.5">
          {overdue > 0 && (
            <Badge tone="danger">{t('vax.summary_overdue').replace('{n}', String(overdue))}</Badge>
          )}
          {pending - overdue > 0 && (
            <Badge tone="warn">
              {t('vax.summary_pending').replace('{n}', String(pending - overdue))}
            </Badge>
          )}
          {pending === 0 && <Badge tone="ok">{t('vax.summary_upto')}</Badge>}
        </div>
        <div className="flex-1" />
        <Button variant="outline" onClick={() => openPrint(`vaccination-card/${patientId}`)}>
          <Printer className="h-4 w-4" />
          {t('pr.btn.vaccination_card')}
        </Button>
        {canRecord && (
          <Button variant="accent" onClick={() => setPreset({})}>
            <Plus className="h-4 w-4" />
            {t('vax.record')}
          </Button>
        )}
      </div>

      {STAGES.map((stage) => {
        const rows = byStage.get(stage)
        if (!rows?.length) return null
        return (
          <Card key={stage} className="overflow-hidden">
            <div className="flex items-baseline justify-between gap-3 border-b border-line bg-surface-2/60 px-5 py-2.5">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-tx-3">
                {t(`vax.stage.${stage}`)}
              </h3>
              {stage === 'indicated' && (
                <span className="text-[11px] text-tx-4">{t('vax.stage.indicated_hint')}</span>
              )}
            </div>
            <div className="divide-y divide-line-soft">
              {rows.map((row) => (
                <DoseRow
                  key={row.dose.key}
                  row={row}
                  onRecord={
                    canRecord &&
                    (row.dose.repeat_months != null || row.state.status !== 'administered')
                      ? () => setPreset({ vaccine: row.dose.vaccine, dose: row.dose.key })
                      : undefined
                  }
                />
              ))}
            </div>
          </Card>
        )
      })}

      {hidden > 0 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="inline-flex items-center gap-1.5 text-[13px] text-tx-3 hover:text-tx"
        >
          <ChevronDown className={cn('h-4 w-4 transition-transform', showAll && 'rotate-180')} />
          {showAll ? t('vax.hide_na') : t('vax.show_na').replace('{n}', String(hidden))}
        </button>
      )}

      {/* History */}
      <div>
        <h3 className="mb-3 text-[13px] font-medium uppercase tracking-wide text-tx-3">
          {t('vax.history')}
        </h3>
        <Card>
          {card.records.length === 0 ? (
            <EmptyState icon={Syringe} title={t('vax.history_empty')} />
          ) : (
            <div className="divide-y divide-line-soft">
              {card.records.map((r) => (
                <HistoryRow
                  key={r.id}
                  record={r}
                  dose={catalog.doses.find((d) => d.key === r.dose_key)}
                  onVoid={canRecord && !r.voided_at ? () => setVoiding(r) : undefined}
                />
              ))}
            </div>
          )}
        </Card>
      </div>

      <RecordVaccinationModal
        patientId={patientId}
        catalog={catalog}
        states={card.states}
        preset={preset}
        onClose={() => setPreset(null)}
      />
      <VoidVaccinationModal record={voiding} onClose={() => setVoiding(null)} />
    </div>
  )
}

function DoseRow({ row, onRecord }: { row: Row; onRecord?: () => void }) {
  const t = useT()
  const { dose, state } = row
  const muted = state.status === 'not_applicable'
  const when =
    state.status === 'administered' ||
    state.status === 'refused' ||
    state.status === 'contraindicated'
      ? state.last_on && t('vax.given_on').replace('{date}', fmtDate(state.last_on))
      : state.status === 'overdue' || state.status === 'due'
        ? state.due_on && t('vax.due_since').replace('{date}', fmtDate(state.due_on))
        : state.due_on && t('vax.due_on').replace('{date}', fmtDate(state.due_on))

  return (
    <div
      className={cn(
        'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_8.5rem_minmax(0,1fr)_6.5rem]',
        muted && 'opacity-55',
      )}
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-tx">{vaccineName(t, dose.vaccine)}</p>
        <p className="truncate text-xs text-tx-3">{vaccineDiseases(t, dose.vaccine)}</p>
      </div>
      <div className="hidden text-[13px] text-tx-2 sm:block">
        {doseLabel(t, dose)}
        <span className="block text-xs text-tx-4">
          {dose.repeat_months
            ? t('vax.age.from').replace('{age}', ageLabel(t, dose.age_months))
            : ageLabel(t, dose.age_months)}
        </span>
      </div>
      <div>
        <Badge tone={STATUS_TONE[state.status]}>{t(`vax.status.${state.status}`)}</Badge>
      </div>
      <div className="hidden text-[13px] text-tx-3 sm:block">
        {when || '—'}
        {/* A periodic dose shows when the last one was given under the next due date. */}
        {dose.repeat_months && state.status !== 'administered' && state.last_on && state.due_on && (
          <span className="block text-xs text-tx-4">
            {t('vax.given_on').replace('{date}', fmtDate(state.last_on))}
          </span>
        )}
      </div>
      <div className="hidden justify-end sm:flex">
        {onRecord && (
          <Button size="sm" variant="ghost" onClick={onRecord} title={t('vax.record_this')}>
            <Plus className="h-3.5 w-3.5" />
            {t('vax.record_short')}
          </Button>
        )}
      </div>
    </div>
  )
}

function HistoryRow({
  record: r,
  dose,
  onVoid,
}: {
  record: VaccinationRecord
  dose?: ScheduledDose
  onVoid?: () => void
}) {
  const t = useT()
  const voided = !!r.voided_at
  const tone = r.outcome === 'administered' ? 'ok' : 'warn'
  const details = [
    dose && doseLabel(t, dose),
    r.lot && `${t('vax.lot')} ${r.lot}`,
    r.route && t(`vax.route.${r.route}`),
    r.site && t(`vax.site.${r.site}`),
  ].filter(Boolean)

  return (
    <div className="flex items-start gap-4 px-5 py-3.5">
      <div
        className={cn(
          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          voided ? 'bg-surface-2 text-tx-4' : 'bg-[var(--accent-10)] text-accent',
        )}
      >
        {voided ? (
          <Ban className="h-4 w-4" />
        ) : r.source === 'clinic' ? (
          <Building2 className="h-4 w-4" />
        ) : (
          <FileText className="h-4 w-4" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className={cn('text-sm font-medium text-tx', voided && 'text-tx-4 line-through')}>
            {vaccineName(t, r.vaccine_code)}
          </p>
          {!voided && <Badge tone={tone}>{t(`vax.outcome.${r.outcome}`)}</Badge>}
          {r.source === 'external' && <Badge tone="neutral">{t('vax.external_short')}</Badge>}
        </div>
        <p className={cn('mt-0.5 text-xs text-tx-3', voided && 'line-through')}>
          <span className="font-mono">{fmtDate(r.occurred_on)}</span>
          {details.length > 0 && ` · ${details.join(' · ')}`}
          {r.recorded_by_name && ` · ${t('vax.by').replace('{name}', r.recorded_by_name)}`}
        </p>
        {r.notes && !voided && <p className="mt-1 text-xs text-tx-2">{r.notes}</p>}
        {voided && (
          <p className="mt-1 text-xs text-danger">
            {t('vax.voided_by')
              .replace('{name}', r.voided_by_name ?? '—')
              .replace('{reason}', r.void_reason ?? '')}
          </p>
        )}
      </div>
      {onVoid && (
        <Menu
          label={t('app.actions')}
          items={[{ label: t('vax.void'), icon: Ban, onSelect: onVoid, tone: 'danger' }]}
        />
      )}
    </div>
  )
}

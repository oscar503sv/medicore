import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Clock, Plus, RotateCw, Save, Search, Trash2, X } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { consultationsApi } from '@/api/consultations'
import { diagnosesApi } from '@/api/diagnoses'
import { noteTemplatesApi } from '@/api/noteTemplates'
import { ConsultationApplications } from '@/components/applications/ConsultationApplications'
import { ConsultationRail, type RailSection } from '@/components/consultation/ConsultationRail'
import { NoteEditor } from '@/components/consultation/NoteEditor'
import { ConsultationProcedures } from '@/components/procedures/ConsultationProcedures'
import { ConsultationExams } from '@/components/records/ConsultationExams'
import { RecordPrintActions } from '@/components/records/RecordDocuments'
import { Badge } from '@/components/ui/Badge'
import { typeTone } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { unitLabel } from '@/components/patients/vitalsData'
import { fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { sectionTitle } from '@/lib/notes'
import { useAuthStore } from '@/stores/auth'
import type { ClinicalNote, Consultation, MedicalRecord, Vitals } from '@/types'

const VITAL_FIELDS: {
  key: keyof Vitals
  labelKey: string
  placeholder: string
  unit: string // literal unit or a `vital.unit_*` i18n key
}[] = [
  { key: 'blood_pressure', labelKey: 'vital.blood_pressure', placeholder: '120/80', unit: 'mmHg' },
  { key: 'heart_rate', labelKey: 'vital.heart_rate', placeholder: '72', unit: 'vital.unit_bpm' },
  { key: 'spo2', labelKey: 'vital.spo2', placeholder: '98', unit: '%' },
  { key: 'temperature', labelKey: 'vital.temperature', placeholder: '36.5', unit: '°C' },
  { key: 'weight', labelKey: 'vital.weight', placeholder: '70', unit: 'kg' },
  { key: 'glucose', labelKey: 'vital.glucose_full', placeholder: '90', unit: 'mg/dL' },
]

// Same rule as the backend: required note sections 60%, a diagnosis 20%, any vital 20%;
// signing needs at least MIN_TO_SIGN.
const MIN_TO_SIGN = 60
const SAVE_DELAY_MS = 800

type Patch = { vitals?: Vitals; note?: Record<string, string> }
type SaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error'

const hasVitals = (v: Vitals) => Object.values(v).some((x) => x !== null && x !== '')

function completionOf(note: ClinicalNote, texts: Record<string, string>, dx: number, v: Vitals) {
  const counted = note.sections.filter((s) => s.required)
  const pool = counted.length ? counted : note.sections
  const filled = pool.filter((s) => (texts[s.key] ?? '').trim()).length
  return Math.round((filled / pool.length) * 60 + (dx ? 20 : 0) + (hasVitals(v) ? 20 : 0))
}

/**
 * Debounced autosave of the draft: edits accumulate in a pending patch sent after a pause;
 * ``flush`` sends it right away (before signing, switching templates or leaving) and
 * resolves once the server has it. A failed save keeps the patch to retry.
 */
function useAutosave(id: string, onSaved: (c: Consultation) => void) {
  const t = useT()
  const pending = useRef<Patch>({})
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const inflight = useRef<Promise<void> | null>(null)
  const [state, setState] = useState<SaveState>('idle')
  const stateRef = useRef<SaveState>('idle')
  const setBoth = (s: SaveState) => {
    stateRef.current = s
    setState(s)
  }

  const flush = useCallback(async (): Promise<void> => {
    clearTimeout(timer.current)
    if (inflight.current) await inflight.current.catch(() => undefined)
    const patch = pending.current
    if (!patch.vitals && !patch.note) return
    pending.current = {}
    setBoth('saving')
    const request = consultationsApi
      .autosave(id, patch)
      .then((c) => {
        onSaved(c)
        setBoth(pending.current.vitals || pending.current.note ? 'pending' : 'saved')
      })
      .catch((err) => {
        // Keep what failed, under anything typed since, to retry.
        pending.current = {
          vitals: pending.current.vitals ?? patch.vitals,
          note: { ...patch.note, ...pending.current.note },
        }
        if (stateRef.current !== 'error') toast(errorMessage(err), 'danger')
        setBoth('error')
        throw err
      })
    inflight.current = request
    try {
      await request
    } finally {
      if (inflight.current === request) inflight.current = null
    }
  }, [id, onSaved])

  const queue = useCallback(
    (patch: Patch) => {
      pending.current = {
        vitals: patch.vitals ?? pending.current.vitals,
        note: patch.note ? { ...pending.current.note, ...patch.note } : pending.current.note,
      }
      if (stateRef.current !== 'error') setBoth('pending')
      clearTimeout(timer.current)
      timer.current = setTimeout(() => void flush().catch(() => undefined), SAVE_DELAY_MS)
    },
    [flush],
  )

  // Leaving the screen saves what is pending; closing the tab with unsaved text warns.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (pending.current.vitals || pending.current.note || inflight.current) {
        e.preventDefault()
        e.returnValue = t('consult.unsaved_leave')
      }
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
      void flush().catch(() => undefined)
    }
  }, [flush, t])

  return { state, queue, flush }
}

export function ConsultationPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { id = '' } = useParams()
  // Optional modules: their sections only show when the clinic has contracted them (or a
  // draft was already added before the module was dropped).
  const canApplications = useAuthStore((s) => s.can('applications.view'))
  const canProcedures = useAuthStore((s) => s.can('procedures.view'))

  const { data, isLoading } = useQuery({
    queryKey: ['consultation', id],
    queryFn: () => consultationsApi.get(id).catch(() => null),
  })
  const { data: catalog } = useQuery({
    queryKey: ['note-catalog'],
    queryFn: noteTemplatesApi.catalog,
    staleTime: 5 * 60 * 1000,
  })

  // Local editable state (mirrors the consultation; autosaved with debounce).
  const [vitals, setVitals] = useState<Vitals | null>(null)
  const [note, setNote] = useState<ClinicalNote | null>(null)
  const [texts, setTexts] = useState<Record<string, string>>({})
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [signOpen, setSignOpen] = useState(false)
  const [signed, setSigned] = useState<MedicalRecord | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const loadNote = (n: ClinicalNote) => {
    setNote(n)
    setTexts(Object.fromEntries(n.sections.map((s) => [s.key, s.text])))
  }

  // Initialize local state once the consultation loads.
  useEffect(() => {
    if (data && vitals === null) {
      setVitals(data.vitals)
      loadNote(data.note)
      setSavedAt(data.last_saved_at)
    }
  }, [data, vitals])

  // Live timer, counted from when the consultation started (survives reloads).
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [])

  const onSaved = useCallback(
    (c: Consultation) => {
      qc.setQueryData(['consultation', id], c)
      setSavedAt(c.last_saved_at)
    },
    [qc, id],
  )
  const save = useAutosave(id, onSaved)

  const switchTemplate = useMutation({
    mutationFn: async (template: string) => {
      await save.flush()
      return consultationsApi.changeTemplate(id, template)
    },
    onSuccess: (c) => {
      qc.setQueryData(['consultation', id], c)
      loadNote(c.note)
      toast(t('note.switched'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const favourite = useMutation({
    mutationFn: (template: string | null) => noteTemplatesApi.setFavourite(template),
    onSuccess: (c) => {
      qc.setQueryData(['note-catalog'], c)
      if (c.favourite) toast(t('note.favourite_saved'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const sign = useMutation({
    mutationFn: async () => {
      await save.flush() // never sign without the last keystrokes
      return consultationsApi.sign(id)
    },
    onSuccess: (record) => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['records'] })
      toast(t('consult.signed_ok'))
      setSignOpen(false)
      setSigned(record) // offer the patient's documents before leaving
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading) return <PageLoader />
  if (!data || !vitals || !note) {
    return <div className="p-8 text-sm text-tx-3">{t('consult.not_found')}</div>
  }

  const elapsed = Math.max(0, Math.floor((now - Date.parse(data.started_at)) / 1000))
  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')
  const patient = data.patient
  const appt = data.appointment
  const completion = completionOf(note, texts, data.diagnoses.length, vitals)
  const missingSections = note.sections.filter((s) => s.required && !(texts[s.key] ?? '').trim())
  const missing = [
    ...missingSections.map((s) => sectionTitle(t, note.template, s)),
    ...(data.diagnoses.length ? [] : [t('consult.missing.diagnosis')]),
    ...(hasVitals(vitals) ? [] : [t('consult.missing.vitals')]),
  ]
  const railSections: RailSection[] = [
    { id: 'sec-vitals', label: t('consult.vitals'), done: hasVitals(vitals) },
    { id: 'sec-note', label: t('note.title'), done: missingSections.length === 0 },
    {
      id: 'sec-diagnoses',
      label: t('consult.diagnoses'),
      done: data.diagnoses.length > 0,
      count: data.diagnoses.length,
    },
    {
      id: 'sec-prescriptions',
      label: t('consult.prescriptions'),
      optional: true,
      count: data.draft_prescriptions.length,
    },
    { id: 'sec-exams', label: t('exam.title'), optional: true, count: data.draft_exams.length },
  ]
  const showApplications = canApplications || data.draft_applications.length > 0
  const showProcedures = canProcedures || data.draft_procedures.length > 0
  if (showApplications) {
    railSections.push({
      id: 'sec-applications',
      label: t('apl.consult_title'),
      optional: true,
      count: data.draft_applications.length,
    })
  }
  if (showProcedures) {
    railSections.push({
      id: 'sec-procedures',
      label: t('prc.consult_title'),
      optional: true,
      count: data.draft_procedures.length,
    })
  }

  async function leave() {
    try {
      await save.flush()
    } catch {
      if (!window.confirm(t('consult.unsaved_leave'))) return
    }
    navigate(-1)
  }

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header */}
      <header className="flex items-center justify-between border-b border-line bg-surface px-6 py-3">
        <div className="flex items-center gap-4">
          <button
            onClick={leave}
            aria-label={t('consult.exit')}
            className="rounded-md p-1.5 text-tx-3 hover:bg-surface-2"
          >
            <X className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 animate-pulse-dot rounded-pill bg-warn" />
            <span className="text-[13px] font-medium text-tx-2">{t('consult.in_progress')}</span>
          </div>
          <span className="flex items-center gap-1.5 font-mono text-sm text-tx-2">
            <Clock className="h-3.5 w-3.5 text-tx-4" />
            {mm}:{ss}
            {appt && (
              <span className="text-tx-4">
                {' '}/ {appt.duration_minutes} min {t('consult.scheduled')}
              </span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <SaveStatus
            state={save.state}
            savedAt={savedAt}
            onRetry={() => void save.flush().catch(() => undefined)}
          />
          <Button onClick={() => setSignOpen(true)}>{t('consult.sign')}</Button>
        </div>
      </header>

      {/* Patient context bar */}
      {patient && (
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 border-b border-line bg-surface-2/30 px-6 py-3">
          <div>
            <p className="font-medium text-tx">
              {patient.first_name} {patient.last_name}
            </p>
            <p className="font-mono text-xs text-tx-3">{patient.code}</p>
          </div>
          <Meta label={t('consult.age')}>
            {t('consult.years_short').replace('{n}', String(patient.age))} ·{' '}
            {t(`sex.${patient.sex}`)}
          </Meta>
          <Meta label={t('consult.blood_type')}>{patient.blood_type ?? '—'}</Meta>
          <Meta label={t('consult.allergies')}>
            {patient.allergies.length > 0 ? (
              <span className="inline-flex items-center gap-1 text-danger">
                <AlertTriangle className="h-3.5 w-3.5" />
                {patient.allergies.join(', ')}
              </span>
            ) : (
              <span className="text-tx-3">{t('consult.no_allergies')}</span>
            )}
          </Meta>
          {appt && (
            <Meta label={t('consult.reason')}>
              <span className="inline-flex items-center gap-2">
                <Badge tone={typeTone(appt.type)}>{t(`apptype.${appt.type}`)}</Badge>
                <span className="text-tx">{appt.reason}</span>
              </span>
            </Meta>
          )}
        </div>
      )}

      {/* Body: the record on the left, guidance and patient context on the right */}
      <div className="grid flex-1 grid-cols-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[1fr_280px]">
        <div className="min-w-0 space-y-6">
          {/* Vitals */}
          <section id="sec-vitals" className="scroll-mt-4">
            <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.vitals')}</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {VITAL_FIELDS.map((f) => (
                <label
                  key={f.key}
                  className="rounded-lg border border-line bg-surface p-3 focus-within:border-accent"
                >
                  <span className="eyebrow mb-1 block">{t(f.labelKey)}</span>
                  <span className="flex items-baseline gap-1.5">
                    <input
                      value={(vitals[f.key] as string | number | null) ?? ''}
                      onChange={(e) => {
                        const next = { ...vitals, [f.key]: e.target.value || null }
                        setVitals(next)
                        save.queue({ vitals: next })
                      }}
                      placeholder={f.placeholder}
                      inputMode={f.key === 'blood_pressure' ? 'text' : 'decimal'}
                      className="w-full min-w-0 bg-transparent font-serif text-2xl text-tx placeholder:text-tx-4 focus:outline-none"
                    />
                    <span className="shrink-0 text-xs text-tx-3">{unitLabel(t, f.unit)}</span>
                  </span>
                </label>
              ))}
            </div>
          </section>

          <NoteEditor
            note={note}
            texts={texts}
            catalog={catalog}
            switching={switchTemplate.isPending}
            onChange={(key, text) => {
              setTexts((prev) => ({ ...prev, [key]: text }))
              save.queue({ note: { [key]: text } })
            }}
            onSwitch={(template) => switchTemplate.mutate(template)}
            onFavourite={(template) => favourite.mutate(template)}
          />

          <DiagnosesSection consultationId={id} consultation={data} />
          <PrescriptionsSection consultationId={id} consultation={data} />
          <div id="sec-exams" className="scroll-mt-4">
            <ConsultationExams consultationId={id} consultation={data} />
          </div>
          {showApplications && (
            <div id="sec-applications" className="scroll-mt-4">
              <ConsultationApplications consultationId={id} consultation={data} />
            </div>
          )}
          {showProcedures && (
            <div id="sec-procedures" className="scroll-mt-4">
              <ConsultationProcedures consultationId={id} consultation={data} />
            </div>
          )}
        </div>

        <ConsultationRail
          completion={completion}
          sections={railSections}
          patient={patient}
          consultationId={id}
        />
      </div>

      {/* Sign modal: what is still missing, and the hard floor */}
      <Modal open={signOpen} onClose={() => setSignOpen(false)} title={t('consult.sign')}>
        <div className="space-y-4 p-5">
          {completion < MIN_TO_SIGN ? (
            <div className="rounded-lg bg-[var(--danger-10)] px-3 py-2 text-[13px] text-danger">
              {t('consult.sign_blocked')
                .replace('{n}', String(completion))
                .replace('{min}', String(MIN_TO_SIGN))}
            </div>
          ) : null}
          {missing.length > 0 && (
            <div className="rounded-lg bg-[var(--warn-10)] px-3 py-2 text-[13px] text-warn">
              <p className="font-medium">{t('consult.sign_missing')}</p>
              <ul className="mt-1 list-disc pl-5">
                {missing.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-sm text-tx-2">
            {missing.length === 0 ? t('consult.sign_confirm') : t('consult.sign_irreversible')}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setSignOpen(false)}>
              {t('app.cancel')}
            </Button>
            <Button
              loading={sign.isPending}
              disabled={completion < MIN_TO_SIGN}
              onClick={() => sign.mutate()}
            >
              {t('consult.sign')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* After signing: print what the patient takes home */}
      <Modal
        open={!!signed}
        onClose={() => navigate('/appointments')}
        title={t('pr.after_sign_title')}
      >
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('pr.after_sign_desc')}</p>
          {signed && <RecordPrintActions record={signed} />}
          <div className="flex justify-end">
            <Button onClick={() => navigate('/appointments')}>{t('pr.after_sign_done')}</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function SaveStatus({
  state,
  savedAt,
  onRetry,
}: {
  state: SaveState
  savedAt: string | null
  onRetry: () => void
}) {
  const t = useT()
  if (state === 'error') {
    return (
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-1.5 text-xs text-danger hover:underline"
      >
        <AlertTriangle className="h-3.5 w-3.5" />
        {t('consult.save_failed')} · {t('consult.retry')}
        <RotateCw className="h-3 w-3" />
      </button>
    )
  }
  const label =
    state === 'saving' || state === 'pending'
      ? t('consult.saving')
      : savedAt
        ? t('consult.saved_at').replace('{time}', fmtTime(savedAt))
        : t('consult.autosaved')
  return (
    <span className="flex items-center gap-1.5 text-xs text-tx-3" aria-live="polite">
      <Save className="h-3.5 w-3.5" />
      {label}
    </span>
  )
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="eyebrow mb-0.5">{label}</p>
      <div className="text-sm text-tx">{children}</div>
    </div>
  )
}

function DiagnosesSection({
  consultationId,
  consultation,
}: {
  consultationId: string
  consultation: Consultation
}) {
  const t = useT()
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)

  // Debounce the search input so we don't hit the catalog on every keystroke.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 250)
    return () => clearTimeout(id)
  }, [query])

  const { data: config } = useQuery({
    queryKey: ['diagnosis-config'],
    queryFn: diagnosesApi.config,
    staleTime: 5 * 60 * 1000,
  })

  // Backend requires >= 2 chars; below that the dropdown stays closed.
  const { data: suggestions = [], isFetching } = useQuery({
    queryKey: ['diagnosis-search', config?.version, debounced],
    queryFn: () => diagnosesApi.search(debounced),
    enabled: debounced.length >= 2,
  })

  // Keyboard navigation: arrows move the highlight, Enter adds, Escape closes.
  const [active, setActive] = useState(-1)
  useEffect(() => setActive(-1), [debounced])

  const add = useMutation({
    mutationFn: ({ code, label }: { code: string; label: string }) =>
      consultationsApi.addDiagnosis(consultationId, code, label),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setQuery('')
      setDebounced('')
      setOpen(false)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (dx: string) => consultationsApi.removeDiagnosis(consultationId, dx),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
  })

  const added = new Set(consultation.diagnoses.map((d) => d.code))
  const versionLabel = `${t('consult.icd_prefix')}-${config?.version === 'cie10' ? '10' : '11'}`

  return (
    <section id="sec-diagnoses" className="scroll-mt-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-tx">
          {t('consult.diagnoses')} <span className="text-tx-3">· {versionLabel}</span>
        </h3>
        <span className="text-xs text-tx-3">
          {consultation.diagnoses.length} {t('consult.dx_unit')}
        </span>
      </div>

      {/* Search box + suggestions dropdown */}
      <div className="relative">
        <div className="relative flex items-center">
          <Search className="absolute left-3 h-4 w-4 text-tx-4" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setOpen(false)
                return
              }
              if (!open || suggestions.length === 0) return
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setActive((a) => (a + 1) % suggestions.length)
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setActive((a) => (a <= 0 ? suggestions.length - 1 : a - 1))
              } else if (e.key === 'Enter') {
                e.preventDefault()
                const s = suggestions[active >= 0 ? active : 0]
                if (s && !added.has(s.code) && !add.isPending) {
                  add.mutate({ code: s.code, label: s.label })
                }
              }
            }}
            placeholder={t('consult.dx_search')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        {open && debounced.length >= 2 && (
          <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-line bg-surface shadow-lg">
            {suggestions.length === 0 ? (
              <p className="px-3 py-3 text-[13px] text-tx-3">
                {isFetching ? t('consult.dx_searching') : t('consult.dx_no_results')}
              </p>
            ) : (
              suggestions.map((s, idx) => {
                const already = added.has(s.code)
                return (
                  <button
                    key={`${s.version}:${s.code}`}
                    type="button"
                    disabled={already || add.isPending}
                    ref={(el) => {
                      if (idx === active) el?.scrollIntoView({ block: 'nearest' })
                    }}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setActive(idx)}
                    onClick={() => add.mutate({ code: s.code, label: s.label })}
                    className={`flex w-full items-center gap-3 px-3 py-2 text-left transition-colors disabled:opacity-40 ${
                      idx === active ? 'bg-surface-2' : ''
                    }`}
                  >
                    <span className="rounded bg-[var(--accent-10)] px-1.5 py-0.5 font-mono text-[12px] font-medium text-accent">
                      {s.code}
                    </span>
                    <span className="flex-1">
                      <span className="block text-sm text-tx">{s.label}</span>
                      {s.chapter && (
                        <span className="block truncate text-[11px] text-tx-4">{s.chapter}</span>
                      )}
                    </span>
                    {!s.billable && (
                      <span className="shrink-0 rounded border border-line px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-tx-3">
                        {t('consult.dx_category')}
                      </span>
                    )}
                    <Plus className="h-4 w-4 shrink-0 text-tx-4" />
                  </button>
                )
              })
            )}
          </div>
        )}
      </div>

      {/* Added diagnoses */}
      <div className="mt-3 space-y-2">
        {consultation.diagnoses.map((d) => (
          <div key={d.code} className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2">
            <span className="font-mono text-[13px] font-medium text-accent">{d.code}</span>
            <span className="flex-1 text-sm text-tx">{d.label}</span>
            <button onClick={() => remove.mutate(d.code)} className="text-tx-4 hover:text-danger">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}

function PrescriptionsSection({
  consultationId,
  consultation,
}: {
  consultationId: string
  consultation: Consultation
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState<{ drug: string; dose: string; schedule: string; days: string }>({
    drug: '',
    dose: '',
    schedule: '',
    days: '',
  })

  const add = useMutation({
    mutationFn: () =>
      consultationsApi.addPrescription(consultationId, {
        drug: form.drug,
        dose: form.dose,
        schedule: form.schedule,
        duration_days: form.days ? Number(form.days) : null,
      }),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setForm({ drug: '', dose: '', schedule: '', days: '' })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (index: number) => consultationsApi.removePrescription(consultationId, index),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
  })

  const inputCls =
    'h-9 w-full rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none'

  const allergies = consultation.patient?.allergies ?? []

  return (
    <section id="sec-prescriptions" className="scroll-mt-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-tx">{t('consult.prescriptions')}</h3>
        <span className="text-xs text-tx-3">
          {consultation.draft_prescriptions.length} {t('consult.rx_unit')}
        </span>
      </div>
      <div className="space-y-2">
        {consultation.draft_prescriptions.map((rx, i) => (
          <div key={i} className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2">
            <div className="flex-1">
              <p className="text-sm font-medium text-tx">{rx.drug}</p>
              <p className="text-xs text-tx-3">
                {rx.dose} · {rx.schedule}
                {rx.duration_days ? ` · ${rx.duration_days} ${t('consult.rx_days').toLowerCase()}` : ''}
              </p>
            </div>
            <button onClick={() => remove.mutate(i)} className="text-tx-4 hover:text-danger">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      {/* Enter in any field adds the medication */}
      <form
        className="mt-3 rounded-xl border border-line bg-surface p-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (form.drug.trim() && form.dose.trim() && !add.isPending) add.mutate()
        }}
      >
        {allergies.length > 0 && (
          <p className="mb-3 flex items-center gap-1.5 rounded-lg bg-[var(--danger-10)] px-3 py-2 text-xs text-danger">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            {t('consult.allergy_reminder').replace('{list}', allergies.join(', '))}
          </p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_120px_1fr_88px]">
          <div>
            <label className="eyebrow mb-1 block">{t('consult.rx_drug')}</label>
            <input
              value={form.drug}
              onChange={(e) => setForm({ ...form, drug: e.target.value })}
              placeholder={t('consult.rx_drug_ph')}
              className={inputCls}
            />
          </div>
          <div>
            <label className="eyebrow mb-1 block">{t('consult.rx_dose')}</label>
            <input
              value={form.dose}
              onChange={(e) => setForm({ ...form, dose: e.target.value })}
              placeholder="500 mg"
              className={inputCls}
            />
          </div>
          <div>
            <label className="eyebrow mb-1 block">{t('consult.rx_schedule')}</label>
            <input
              value={form.schedule}
              onChange={(e) => setForm({ ...form, schedule: e.target.value })}
              placeholder={t('consult.rx_schedule_ph')}
              className={inputCls}
            />
          </div>
          <div>
            <label className="eyebrow mb-1 block">{t('consult.rx_days')}</label>
            <input
              type="number"
              min={1}
              value={form.days}
              onChange={(e) => setForm({ ...form, days: e.target.value })}
              placeholder="30"
              className={inputCls}
            />
          </div>
        </div>
        <Button
          type="submit"
          size="sm"
          className="mt-3"
          disabled={!form.drug.trim() || !form.dose.trim()}
          loading={add.isPending}
        >
          <Plus className="h-4 w-4" />
          {t('consult.rx_add')}
        </Button>
      </form>
    </section>
  )
}

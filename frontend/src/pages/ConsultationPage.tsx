import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Clock, Plus, Save, Trash2, X } from 'lucide-react'
import { api, errorMessage } from '@/api/client'
import { consultationsApi } from '@/api/consultations'
import { Badge, typeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Consultation, Patient, Soap, Vitals } from '@/types'

const VITAL_FIELDS: {
  key: keyof Vitals
  label: string
  placeholder: string
  unit: string
}[] = [
  { key: 'blood_pressure', label: 'TA', placeholder: '120/80', unit: 'mmHg' },
  { key: 'heart_rate', label: 'FC', placeholder: '72', unit: 'lpm' },
  { key: 'spo2', label: 'SpO₂', placeholder: '98', unit: '%' },
  { key: 'temperature', label: 'Temp', placeholder: '36.5', unit: '°C' },
  { key: 'weight', label: 'Peso', placeholder: '70', unit: 'kg' },
  { key: 'glucose', label: 'Glucemia', placeholder: '90', unit: 'mg/dL' },
]

const SOAP_FIELDS: { key: keyof Soap; letter: string; labelKey: string; helpKey: string }[] = [
  { key: 'subjective', letter: 'S', labelKey: 'consult.subjective', helpKey: 'consult.soap_sub_help' },
  { key: 'objective', letter: 'O', labelKey: 'consult.objective', helpKey: 'consult.soap_obj_help' },
  { key: 'assessment', letter: 'A', labelKey: 'consult.assessment', helpKey: 'consult.soap_ass_help' },
  { key: 'plan', letter: 'P', labelKey: 'consult.plan', helpKey: 'consult.soap_plan_help' },
]

function sexLabel(sex: Patient['sex']): string {
  return sex === 'male' ? 'Masculino' : sex === 'female' ? 'Femenino' : 'Otro'
}

export function ConsultationPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { id = '' } = useParams()

  const { data, isLoading } = useQuery({
    queryKey: ['consultation', id],
    queryFn: () => api.get<Consultation>(`/consultations/${id}`).then((r) => r.data).catch(() => null),
  })

  // Local editable state (mirrors the consultation; autosaved with debounce).
  const [vitals, setVitals] = useState<Vitals | null>(null)
  const [soap, setSoap] = useState<Soap | null>(null)
  const [completion, setCompletion] = useState(0)
  const [signOpen, setSignOpen] = useState(false)
  const [chiefComplaint, setChiefComplaint] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  // Initialize local state once the consultation loads.
  useEffect(() => {
    if (data && vitals === null) {
      setVitals(data.vitals)
      setSoap(data.soap)
      setCompletion(data.completion_percent)
      // Prefill the sign summary with the reason the appointment was booked for.
      if (data.appointment?.reason) setChiefComplaint(data.appointment.reason)
    }
  }, [data, vitals])

  // Live timer.
  useEffect(() => {
    const tick = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(tick)
  }, [])

  const autosave = useMutation({
    mutationFn: (patch: { vitals?: Partial<Vitals>; soap?: Partial<Soap> }) =>
      consultationsApi.autosave(id, patch),
    onSuccess: (c) => setCompletion(c.completion_percent),
  })

  function scheduleSave(next: { vitals?: Vitals; soap?: Soap }) {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      autosave.mutate({
        vitals: next.vitals ?? undefined,
        soap: next.soap ?? undefined,
      })
    }, 800)
  }

  const sign = useMutation({
    mutationFn: () => consultationsApi.sign(id, { chief_complaint: chiefComplaint }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast('Consulta firmada')
      navigate('/appointments')
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading) return <PageLoader />
  if (!data || !vitals || !soap) {
    return <div className="p-8 text-sm text-tx-3">Consulta no encontrada.</div>
  }

  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')
  const patient = data.patient
  const appt = data.appointment

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header */}
      <header className="flex items-center justify-between border-b border-line bg-surface px-6 py-3">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="rounded-md p-1.5 text-tx-3 hover:bg-surface-2">
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
          <span className="flex items-center gap-1.5 text-xs text-tx-3">
            <Save className="h-3.5 w-3.5" />
            {autosave.isPending ? 'Guardando…' : t('consult.autosaved')}
          </span>
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
            {patient.age} a · {sexLabel(patient.sex)}
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

      {/* Body: 2 columns */}
      <div className="grid flex-1 grid-cols-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[1fr_260px]">
        <div className="space-y-6">
          {/* Vitals */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.vitals')}</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {VITAL_FIELDS.map((f) => (
                <div key={f.key} className="rounded-lg border border-line bg-surface p-3">
                  <p className="eyebrow mb-1">{f.label}</p>
                  <div className="flex items-baseline gap-1.5">
                    <input
                      value={(vitals[f.key] as string | number | null) ?? ''}
                      onChange={(e) => {
                        const next = { ...vitals, [f.key]: e.target.value || null }
                        setVitals(next)
                        scheduleSave({ vitals: next })
                      }}
                      placeholder={f.placeholder}
                      className="w-full min-w-0 bg-transparent font-serif text-2xl text-tx placeholder:text-tx-4 focus:outline-none"
                    />
                    <span className="shrink-0 text-xs text-tx-3">{f.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* SOAP 2x2 — each section labelled with a helper note */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.soap')}</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {SOAP_FIELDS.map((f) => (
                <div key={f.key} className="rounded-xl border border-line bg-surface p-4">
                  <div className="mb-2 flex items-start gap-2.5">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-surface-2 font-serif text-sm text-accent">
                      {f.letter}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-tx">{t(f.labelKey)}</p>
                      <p className="text-xs leading-snug text-tx-3">{t(f.helpKey)}</p>
                    </div>
                  </div>
                  <textarea
                    value={soap[f.key]}
                    onChange={(e) => {
                      const next = { ...soap, [f.key]: e.target.value }
                      setSoap(next)
                      scheduleSave({ soap: next })
                    }}
                    rows={4}
                    placeholder={t('app.write_here')}
                    className="w-full resize-none rounded-lg border border-line bg-bg p-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
                  />
                </div>
              ))}
            </div>
          </section>

          <DiagnosesSection consultationId={id} consultation={data} />
          <PrescriptionsSection consultationId={id} consultation={data} />
        </div>

        {/* Right rail: completion ring */}
        <aside className="space-y-4">
          <div className="rounded-lg border border-line bg-surface p-5 text-center">
            <CompletionRing percent={completion} />
            <p className="mt-3 text-[13px] text-tx-3">{t('consult.completion')}</p>
          </div>
        </aside>
      </div>

      {/* Sign modal */}
      <Modal open={signOpen} onClose={() => setSignOpen(false)} title={t('consult.sign')}>
        <div className="space-y-4 p-5">
          {completion < 80 && (
            <div className="rounded-lg bg-[var(--warn-10)] px-3 py-2 text-[13px] text-warn">
              {t('consult.sign_warning')}
            </div>
          )}
          <Input
            label="Motivo de consulta"
            value={chiefComplaint}
            onChange={(e) => setChiefComplaint(e.target.value)}
            placeholder="Resumen del encuentro"
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setSignOpen(false)}>
              {t('app.cancel')}
            </Button>
            <Button loading={sign.isPending} onClick={() => sign.mutate()}>
              {t('consult.sign')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
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

function CompletionRing({ percent }: { percent: number }) {
  const r = 40
  const c = 2 * Math.PI * r
  const offset = c - (percent / 100) * c
  return (
    <svg viewBox="0 0 100 100" className="mx-auto h-28 w-28">
      <circle cx="50" cy="50" r={r} fill="none" stroke="var(--line)" strokeWidth="8" />
      <circle
        cx="50"
        cy="50"
        r={r}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform="rotate(-90 50 50)"
        style={{ transition: 'stroke-dashoffset .4s ease' }}
      />
      <text x="50" y="56" textAnchor="middle" className="fill-tx font-serif text-2xl">
        {percent}%
      </text>
    </svg>
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
  const [code, setCode] = useState('')
  const [label, setLabel] = useState('')

  const add = useMutation({
    mutationFn: () => consultationsApi.addDiagnosis(consultationId, code, label),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setCode('')
      setLabel('')
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (dx: string) => consultationsApi.removeDiagnosis(consultationId, dx),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
  })

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-tx">{t('consult.diagnoses')}</h3>
        <span className="text-xs text-tx-3">
          {consultation.diagnoses.length} {t('consult.dx_unit')}
        </span>
      </div>
      <div className="space-y-2">
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
      <div className="mt-2 flex items-end gap-2">
        <div className="w-24">
          <label className="eyebrow mb-1 block">{t('consult.dx_code')}</label>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="I10"
            className="h-9 w-full rounded-lg border border-line bg-bg px-2 font-mono text-[13px] focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex-1">
          <label className="eyebrow mb-1 block">{t('consult.dx_desc')}</label>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Hipertensión esencial"
            className="h-9 w-full rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none"
          />
        </div>
        <Button size="sm" variant="outline" disabled={!code || !label} onClick={() => add.mutate()}>
          <Plus className="h-4 w-4" />
        </Button>
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

  return (
    <section>
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
      <div className="mt-3 rounded-xl border border-line bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_120px_1fr_88px]">
          <div>
            <label className="eyebrow mb-1 block">{t('consult.rx_drug')}</label>
            <input
              value={form.drug}
              onChange={(e) => setForm({ ...form, drug: e.target.value })}
              placeholder="Ej. Paracetamol"
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
              placeholder="1× día · mañana"
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
          size="sm"
          className="mt-3"
          disabled={!form.drug || !form.dose}
          onClick={() => add.mutate()}
        >
          <Plus className="h-4 w-4" />
          {t('consult.rx_add')}
        </Button>
      </div>
    </section>
  )
}

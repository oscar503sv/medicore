import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Save, Trash2, X } from 'lucide-react'
import { api, errorMessage } from '@/api/client'
import { consultationsApi } from '@/api/consultations'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Consultation, Soap, Vitals } from '@/types'

const VITAL_FIELDS: { key: keyof Vitals; label: string; placeholder: string }[] = [
  { key: 'blood_pressure', label: 'TA', placeholder: '120/80' },
  { key: 'heart_rate', label: 'FC', placeholder: '72' },
  { key: 'spo2', label: 'SpO₂', placeholder: '98' },
  { key: 'temperature', label: 'Temp', placeholder: '36.5' },
  { key: 'weight', label: 'Peso', placeholder: '70' },
  { key: 'glucose', label: 'Glucemia', placeholder: '90' },
]

const SOAP_FIELDS: { key: keyof Soap; labelKey: string }[] = [
  { key: 'subjective', labelKey: 'consult.subjective' },
  { key: 'objective', labelKey: 'consult.objective' },
  { key: 'assessment', labelKey: 'consult.assessment' },
  { key: 'plan', labelKey: 'consult.plan' },
]

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
          <span className="font-mono text-sm text-tx-3">{mm}:{ss}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs text-tx-3">
            <Save className="h-3.5 w-3.5" />
            {autosave.isPending ? 'Guardando…' : t('consult.autosaved')}
          </span>
          <Button onClick={() => setSignOpen(true)}>{t('consult.sign')}</Button>
        </div>
      </header>

      {/* Body: 3 columns */}
      <div className="grid flex-1 grid-cols-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[1fr_260px]">
        <div className="space-y-6">
          {/* Vitals */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.vitals')}</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {VITAL_FIELDS.map((f) => (
                <div key={f.key} className="rounded-lg border border-line bg-surface p-3">
                  <p className="eyebrow mb-1">{f.label}</p>
                  <input
                    value={(vitals[f.key] as string | number | null) ?? ''}
                    onChange={(e) => {
                      const next = { ...vitals, [f.key]: e.target.value || null }
                      setVitals(next)
                      scheduleSave({ vitals: next })
                    }}
                    placeholder={f.placeholder}
                    className="w-full bg-transparent font-serif text-2xl text-tx placeholder:text-tx-4 focus:outline-none"
                  />
                </div>
              ))}
            </div>
          </section>

          {/* SOAP 2x2 */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.soap')}</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {SOAP_FIELDS.map((f) => (
                <div key={f.key}>
                  <label className="eyebrow mb-1 block">{t(f.labelKey)}</label>
                  <textarea
                    value={soap[f.key]}
                    onChange={(e) => {
                      const next = { ...soap, [f.key]: e.target.value }
                      setSoap(next)
                      scheduleSave({ soap: next })
                    }}
                    rows={4}
                    className="w-full resize-none rounded-lg border border-line bg-surface p-3 text-sm text-tx focus:border-accent focus:outline-none"
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
            <Button variant="ghost" onClick={() => setSignOpen(false)}>
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
      <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.diagnoses')}</h3>
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
      <div className="mt-2 flex gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="I10"
          className="h-9 w-24 rounded-lg border border-line bg-bg px-2 font-mono text-[13px] focus:border-accent focus:outline-none"
        />
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Descripción"
          className="h-9 flex-1 rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none"
        />
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
  const [form, setForm] = useState({ drug: '', dose: '', schedule: '' })

  const add = useMutation({
    mutationFn: () =>
      consultationsApi.addPrescription(consultationId, { ...form, duration_days: null }),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setForm({ drug: '', dose: '', schedule: '' })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (index: number) => consultationsApi.removePrescription(consultationId, index),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
  })

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold text-tx">{t('consult.prescriptions')}</h3>
      <div className="space-y-2">
        {consultation.draft_prescriptions.map((rx, i) => (
          <div key={i} className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2">
            <div className="flex-1">
              <p className="text-sm font-medium text-tx">{rx.drug}</p>
              <p className="text-xs text-tx-3">
                {rx.dose} · {rx.schedule}
              </p>
            </div>
            <button onClick={() => remove.mutate(i)} className="text-tx-4 hover:text-danger">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-[1fr_80px_1fr_auto] gap-2">
        <input
          value={form.drug}
          onChange={(e) => setForm({ ...form, drug: e.target.value })}
          placeholder="Fármaco"
          className="h-9 rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none"
        />
        <input
          value={form.dose}
          onChange={(e) => setForm({ ...form, dose: e.target.value })}
          placeholder="20 mg"
          className="h-9 rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none"
        />
        <input
          value={form.schedule}
          onChange={(e) => setForm({ ...form, schedule: e.target.value })}
          placeholder="1× día"
          className="h-9 rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none"
        />
        <Button
          size="sm"
          variant="outline"
          disabled={!form.drug || !form.dose}
          onClick={() => add.mutate()}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
    </section>
  )
}

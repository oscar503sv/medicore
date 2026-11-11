import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarPlus,
  CheckCircle2,
  FileSignature,
  FlaskConical,
  PenLine,
  Printer,
  XCircle,
} from 'lucide-react'
import { errorMessage } from '@/api/client'
import { openPrint } from '@/api/printing'
import { patientsApi } from '@/api/patients'
import {
  proceduresApi,
  type Procedure,
  type ProcedureDetail,
  type ProcedureProgress,
} from '@/api/procedures'
import { NewAppointmentModal } from '@/components/appointments/NewAppointmentModal'
import { ReasonModal } from '@/components/applications/ReasonModal'
import { ProcedureFee } from '@/components/procedures/ProcedureFee'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtDate, fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { isOpen, STATUS_TONE, usePerformer } from '@/lib/procedures'
import { useAuthStore } from '@/stores/auth'

type Tri = boolean | null

/** The editable note as form strings; numbers are parsed on save. */
type Form = {
  allergies_reviewed: boolean
  anticoagulants: Tri
  fasting: Tri
  allergy_override: string
  bp_before: string
  hr_before: string
  spo2_before: string
  temp_before: string
  bp_after: string
  hr_after: string
  spo2_after: string
  temp_after: string
  anesthesia: string
  technique: string
  findings: string
  materials: string
  complications: string
  instructions: string
  specimen_sent: boolean
  specimen_description: string
}

const str = (v: string | number | null) => (v === null ? '' : String(v))

function toForm(d: ProcedureDetail): Form {
  const p = d.procedure
  return {
    allergies_reviewed: p.allergies_reviewed,
    anticoagulants: p.anticoagulants,
    fasting: p.fasting,
    allergy_override: str(p.allergy_override),
    bp_before: str(p.bp_before),
    hr_before: str(p.hr_before),
    spo2_before: str(p.spo2_before),
    temp_before: str(p.temp_before),
    bp_after: str(p.bp_after),
    hr_after: str(p.hr_after),
    spo2_after: str(p.spo2_after),
    temp_after: str(p.temp_after),
    anesthesia: str(p.anesthesia),
    // A fresh note starts from the catalog's templates.
    technique: p.technique ?? d.technique_template ?? '',
    findings: str(p.findings),
    materials: str(p.materials),
    complications: str(p.complications),
    instructions: p.instructions ?? d.instructions_template ?? '',
    specimen_sent: p.specimen_sent,
    specimen_description: str(p.specimen_description),
  }
}

const text = (v: string) => v.trim() || null
const num = (v: string) => (v.trim() === '' ? null : Number(v.replace(',', '.')))

function toPayload(f: Form): ProcedureProgress {
  return {
    allergies_reviewed: f.allergies_reviewed,
    anticoagulants: f.anticoagulants,
    fasting: f.fasting,
    allergy_override: text(f.allergy_override),
    bp_before: text(f.bp_before),
    hr_before: num(f.hr_before),
    spo2_before: num(f.spo2_before),
    temp_before: num(f.temp_before),
    bp_after: text(f.bp_after),
    hr_after: num(f.hr_after),
    spo2_after: num(f.spo2_after),
    temp_after: num(f.temp_after),
    anesthesia: text(f.anesthesia),
    technique: text(f.technique),
    findings: text(f.findings),
    materials: text(f.materials),
    complications: text(f.complications),
    instructions: text(f.instructions),
    specimen_sent: f.specimen_sent,
    specimen_description: f.specimen_sent ? text(f.specimen_description) : null,
  }
}

/** One procedure: checklist, consent on paper, the note, signing; read-only once closed. */
export function ProcedureDetailPage() {
  const t = useT()
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const performer = usePerformer()
  const myName = useAuthStore((s) => s.session?.name)
  const canBook = useAuthStore((s) => s.can('appointments.manage'))
  const [form, setForm] = useState<Form | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [amending, setAmending] = useState(false)
  const [booking, setBooking] = useState(false)

  const { data } = useQuery({ queryKey: ['procedure', id], queryFn: () => proceduresApi.get(id) })
  // The form is seeded once per procedure; later refetches don't overwrite what's typed.
  const loadedId = data?.procedure.id
  useEffect(() => {
    if (data) setForm(toForm(data))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedId])

  const { data: patientDetail } = useQuery({
    queryKey: ['patient', data?.patient.id],
    queryFn: () => patientsApi.get(data!.patient.id),
    enabled: booking && !!data,
  })

  const applied = (d: ProcedureDetail, message?: string) => {
    qc.setQueryData(['procedure', id], d)
    qc.invalidateQueries({ queryKey: ['procedures-worklist'] })
    qc.invalidateQueries({ queryKey: ['procedures-patient', d.patient.id] })
    if (message) toast(message)
  }
  const onError = (err: unknown) => toast(errorMessage(err), 'danger')

  const save = useMutation({
    mutationFn: () => proceduresApi.saveProgress(id, toPayload(form!)),
    onSuccess: (d) => applied(d, t('prc.saved_ok')),
    onError,
  })
  const sign = useMutation({
    mutationFn: async () => {
      await proceduresApi.saveProgress(id, toPayload(form!))
      return proceduresApi.sign(id)
    },
    onSuccess: (d) => {
      applied(d, t('prc.signed_ok'))
      setForm(toForm(d))
    },
    // A failed sign may still have saved the progress (e.g. a new allergy alert to answer).
    onError: (err) => {
      qc.invalidateQueries({ queryKey: ['procedure', id] })
      onError(err)
    },
  })
  const cancel = useMutation({
    mutationFn: (reason: string) => proceduresApi.cancel(id, reason),
    onSuccess: (d) => {
      applied(d, t('prc.cancel_ok'))
      setCancelling(false)
    },
    onError,
  })

  if (!data || !form) return <PageLoader />
  const { procedure: p, patient } = data
  const editable = isOpen(p) && performer.can(p.performer)
  const set = (patch: Partial<Form>) => setForm((f) => (f ? { ...f, ...patch } : f))
  const canAmend =
    p.status === 'completed' &&
    performer.canPerform &&
    (performer.isDoctor || myName === p.performed_by_name)

  return (
    <div className="space-y-5 p-8">
      <Link
        to="/procedures"
        className="inline-flex items-center gap-1.5 text-[13px] text-tx-3 hover:text-tx"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('prc.back')}
      </Link>

      {/* Header */}
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-tx">{p.type_name}</h1>
              <Badge tone={STATUS_TONE[p.status]}>{t(`prc.status.${p.status}`)}</Badge>
              {p.requires_consent && <Badge tone="accent">{t('prc.consent_badge')}</Badge>}
              {p.takes_specimen && <Badge tone="info">{t('prc.specimen_badge')}</Badge>}
            </div>
            <p className="mt-1 text-sm text-tx-2">
              <Link
                to={`/patients/${patient.id}?tab=procedures`}
                className="font-medium hover:underline"
              >
                {patient.name}
              </Link>{' '}
              <span className="font-mono text-xs text-tx-3">{patient.code}</span>
              <span className="text-tx-3">
                {' '}
                · {t('vax.age_short').replace('{n}', String(patient.age))}
              </span>
            </p>
            <p className="mt-2 text-sm text-tx">
              <span className="text-tx-3">{t('prc.indication')}: </span>
              {p.indication}
            </p>
            <p className="mt-1 text-xs text-tx-3">
              {t(`prc.source.${p.source}`)}
              {p.ordered_by_name &&
                ` · ${t('prc.ordered_by').replace('{name}', p.ordered_by_name)}`}
              {` · ${fmtDateTimeTz(p.created_at)}`}
              {` · ${t(`prc.performer.${p.performer}`)}`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {p.status !== 'cancelled' && p.requires_consent && (
              <Button variant="outline" size="sm" onClick={() => openPrint(`consent/${p.id}`)}>
                <Printer className="h-4 w-4" />
                {t('pr.btn.consent')}
              </Button>
            )}
            {p.instructions && (
              <Button variant="outline" size="sm" onClick={() => openPrint(`instructions/${p.id}`)}>
                <Printer className="h-4 w-4" />
                {t('pr.btn.instructions')}
              </Button>
            )}
            {p.status !== 'cancelled' && (p.takes_specimen || p.specimen_sent) && (
              <Button variant="outline" size="sm" onClick={() => openPrint(`pathology/${p.id}`)}>
                <Printer className="h-4 w-4" />
                {t('pr.btn.pathology')}
              </Button>
            )}
            {editable && (
              <Button variant="outline" size="sm" onClick={() => setCancelling(true)}>
                <XCircle className="h-4 w-4" />
                {t('prc.cancel')}
              </Button>
            )}
          </div>
        </div>
        {isOpen(p) && !editable && performer.canPerform && (
          <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-tx-2">
            {t('prc.doctor_only_view')}
          </p>
        )}
        {p.status === 'cancelled' && (
          <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-tx-2">
            {t('prc.cancelled_by')
              .replace('{name}', p.cancelled_by_name ?? '—')
              .replace('{reason}', p.cancel_reason ?? '')}
            {p.cancelled_at && (
              <span className="text-tx-3"> · {fmtDateTimeTz(p.cancelled_at)}</span>
            )}
          </p>
        )}
        {p.status === 'completed' && (
          <p className="mt-3 flex items-center gap-1.5 text-[13px] text-ok">
            <CheckCircle2 className="h-4 w-4" />
            {t('prc.signed_by')
              .replace('{name}', p.performed_by_name ?? '—')
              .replace('{when}', fmtDateTimeTz(p.performed_at))}
          </p>
        )}
      </Card>

      <ProcedureFee data={data} />

      {editable ? (
        <EditView data={data} form={form} set={set} />
      ) : (
        <ReadView p={p} allergies={patient.allergies} />
      )}

      {editable && (
        <div className="flex flex-wrap items-center justify-end gap-3">
          <p className="mr-auto text-xs text-tx-3">{t('prc.sign_hint')}</p>
          <Button variant="outline" loading={save.isPending} onClick={() => save.mutate()}>
            {t('prc.save')}
          </Button>
          <Button loading={sign.isPending} onClick={() => sign.mutate()}>
            <FileSignature className="h-4 w-4" />
            {t('prc.sign')}
          </Button>
        </div>
      )}

      {p.status === 'completed' && p.follow_up_on && (
        <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
          <div>
            <p className="text-sm font-semibold text-tx">{t('prc.follow_up')}</p>
            <p className="text-sm text-tx-2">
              {t('prc.follow_up_on').replace('{date}', fmtDate(p.follow_up_on))}
            </p>
          </div>
          {canBook && (
            <Button variant="outline" onClick={() => setBooking(true)}>
              <CalendarPlus className="h-4 w-4" />
              {t('prc.book_follow_up')}
            </Button>
          )}
        </Card>
      )}

      {p.status === 'completed' && (p.amendments.length > 0 || canAmend) && (
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-tx">{t('prc.amendments')}</h2>
            {canAmend && (
              <Button size="sm" variant="outline" onClick={() => setAmending(true)}>
                <PenLine className="h-4 w-4" />
                {t('prc.amend')}
              </Button>
            )}
          </div>
          <div className="space-y-2">
            {p.amendments.map((a, i) => (
              <div key={i} className="rounded-lg border border-line bg-surface-2/40 px-3 py-2">
                <p className="whitespace-pre-wrap text-sm text-tx">{a.text}</p>
                <p className="mt-1 text-xs text-tx-3">
                  {a.reason} ·{' '}
                  {t('prc.amend_by')
                    .replace('{name}', a.by_name ?? '—')
                    .replace('{when}', fmtDateTimeTz(a.at))}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <ReasonModal
        open={cancelling}
        title={t('prc.cancel')}
        description={t('prc.cancel_desc')}
        confirmLabel={t('prc.cancel')}
        loading={cancel.isPending}
        onConfirm={(reason) => cancel.mutate(reason)}
        onClose={() => setCancelling(false)}
      />
      <AmendModal
        open={amending}
        procedureId={id}
        onDone={(d) => {
          applied(d, t('prc.amend_ok'))
          setAmending(false)
        }}
        onClose={() => setAmending(false)}
      />
      {p.follow_up_on && (
        <NewAppointmentModal
          open={booking && !!patientDetail}
          onClose={() => setBooking(false)}
          date={p.follow_up_on}
          initialPatient={patientDetail?.patient ?? null}
          initialType="follow_up"
          initialReason={t('prc.follow_up_reason').replace('{name}', p.type_name)}
        />
      )}
    </div>
  )
}

// ── editing ──────────────────────────────────────────────────────────────────────────────
function Section({
  title,
  children,
  aside,
}: {
  title: string
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-tx">{title}</h2>
        {aside}
      </div>
      {children}
    </Card>
  )
}

function TriState({
  label,
  value,
  onChange,
}: {
  label: string
  value: Tri
  onChange: (v: Tri) => void
}) {
  const t = useT()
  const options: { v: Tri; label: string }[] = [
    { v: true, label: t('prc.yes') },
    { v: false, label: t('prc.no') },
    { v: null, label: t('prc.na') },
  ]
  return (
    <div>
      <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{label}</span>
      <div className="inline-flex rounded-lg border border-line bg-surface p-0.5">
        {options.map((o) => (
          <button
            key={String(o.v)}
            type="button"
            onClick={() => onChange(o.v)}
            className={cn(
              'rounded-md px-3 py-1 text-[13px] font-medium',
              value === o.v ? 'bg-accent text-white' : 'text-tx-2 hover:text-tx',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function Vitals({
  title,
  form,
  set,
  suffix,
}: {
  title?: string
  form: Form
  set: (patch: Partial<Form>) => void
  suffix: 'before' | 'after'
}) {
  const t = useT()
  const key = (k: 'bp' | 'hr' | 'spo2' | 'temp') => `${k}_${suffix}` as const
  return (
    <div>
      {title && <p className="mb-2 text-[13px] font-medium text-tx-2">{title}</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Input
          label={t('prc.bp')}
          placeholder="120/80"
          value={form[key('bp')]}
          onChange={(e) => set({ [key('bp')]: e.target.value })}
        />
        <Input
          label={t('prc.hr')}
          inputMode="numeric"
          value={form[key('hr')]}
          onChange={(e) => set({ [key('hr')]: e.target.value })}
        />
        <Input
          label={t('prc.spo2')}
          inputMode="numeric"
          value={form[key('spo2')]}
          onChange={(e) => set({ [key('spo2')]: e.target.value })}
        />
        <Input
          label={t('prc.temp')}
          inputMode="decimal"
          value={form[key('temp')]}
          onChange={(e) => set({ [key('temp')]: e.target.value })}
        />
      </div>
    </div>
  )
}

function EditView({
  data,
  form,
  set,
}: {
  data: ProcedureDetail
  form: Form
  set: (patch: Partial<Form>) => void
}) {
  const t = useT()
  const { procedure: p, patient } = data
  return (
    <>
      <Section title={t('prc.before')}>
        <div className="space-y-5">
          <div>
            <p className="mb-1.5 text-[13px] font-medium text-tx-2">{t('prc.allergies')}</p>
            {patient.allergies.length > 0 ? (
              <p className="flex items-center gap-1.5 text-sm text-danger">
                <AlertTriangle className="h-4 w-4" />
                {patient.allergies.join(', ')}
              </p>
            ) : (
              <p className="text-sm text-tx-3">{t('prc.no_allergies')}</p>
            )}
            <label className="mt-2 flex items-center gap-2 text-sm text-tx">
              <Checkbox
                checked={form.allergies_reviewed}
                onChange={(e) => set({ allergies_reviewed: e.target.checked })}
              />
              {t('prc.allergies_reviewed')}
            </label>
          </div>
          <div className="flex flex-wrap gap-6">
            <TriState
              label={t('prc.anticoagulants')}
              value={form.anticoagulants}
              onChange={(v) => set({ anticoagulants: v })}
            />
            <TriState
              label={t('prc.fasting')}
              value={form.fasting}
              onChange={(v) => set({ fasting: v })}
            />
          </div>
          <Vitals title={t('prc.vitals_before')} form={form} set={set} suffix="before" />
        </div>
      </Section>

      {p.requires_consent && <ConsentSection data={data} />}

      <Section title={t('prc.note')}>
        <div className="space-y-4">
          <Input
            label={t('prc.anesthesia')}
            placeholder={t('prc.anesthesia_ph')}
            value={form.anesthesia}
            onChange={(e) => set({ anesthesia: e.target.value })}
          />
          {data.allergy_conflicts.length > 0 && (
            <div className="rounded-lg border border-danger/40 bg-[var(--danger-10)] p-3">
              <p className="flex items-center gap-1.5 text-sm font-semibold text-danger">
                <AlertTriangle className="h-4 w-4" />
                {t('prc.allergy_title')}
              </p>
              <p className="mb-2 text-[13px] text-tx-2">
                {t('prc.allergy_desc').replace('{list}', data.allergy_conflicts.join(', '))}
              </p>
              <Input
                label={t('prc.allergy_reason')}
                placeholder={t('prc.allergy_reason_ph')}
                value={form.allergy_override}
                onChange={(e) => set({ allergy_override: e.target.value })}
              />
            </div>
          )}
          <NoteField
            label={t('prc.technique')}
            value={form.technique}
            onChange={(v) => set({ technique: v })}
            template={data.technique_template}
            rows={4}
          />
          <Textarea
            label={t('prc.findings')}
            rows={2}
            value={form.findings}
            onChange={(e) => set({ findings: e.target.value })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t('prc.materials')}
              placeholder={t('prc.materials_ph')}
              value={form.materials}
              onChange={(e) => set({ materials: e.target.value })}
            />
            <Input
              label={t('prc.complications')}
              placeholder={t('prc.complications_ph')}
              value={form.complications}
              onChange={(e) => set({ complications: e.target.value })}
            />
          </div>
          <NoteField
            label={t('prc.instructions')}
            value={form.instructions}
            onChange={(v) => set({ instructions: v })}
            template={data.instructions_template}
            rows={3}
          />
        </div>
      </Section>

      <Section title={t('prc.specimen')}>
        {p.takes_specimen && <p className="mb-2 text-xs text-tx-3">{t('prc.specimen_hint')}</p>}
        <label className="flex items-center gap-2 text-sm text-tx">
          <Checkbox
            checked={form.specimen_sent}
            onChange={(e) => set({ specimen_sent: e.target.checked })}
          />
          <FlaskConical className="h-4 w-4 text-tx-3" />
          {t('prc.specimen_sent')}
        </label>
        {form.specimen_sent && (
          <div className="mt-3">
            <Input
              label={t('prc.specimen_desc')}
              placeholder={t('prc.specimen_desc_ph')}
              value={form.specimen_description}
              onChange={(e) => set({ specimen_description: e.target.value })}
            />
          </div>
        )}
      </Section>

      <Section title={t('prc.vitals_after')}>
        <Vitals form={form} set={set} suffix="after" />
      </Section>
    </>
  )
}

function NoteField({
  label,
  value,
  onChange,
  template,
  rows,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  template: string | null
  rows: number
}) {
  const t = useT()
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[13px] font-medium text-tx-2">{label}</span>
        {template && value !== template && (
          <button
            type="button"
            onClick={() => onChange(template)}
            className="text-xs text-accent hover:underline"
          >
            {t('prc.use_template')}
          </button>
        )}
      </div>
      <Textarea rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

function ConsentSection({ data }: { data: ProcedureDetail }) {
  const t = useT()
  const qc = useQueryClient()
  const p = data.procedure
  const [signer, setSigner] = useState('')
  const [relationship, setRelationship] = useState('')
  const [witness, setWitness] = useState('')
  const record = useMutation({
    mutationFn: () =>
      proceduresApi.consent(p.id, {
        signer: signer.trim(),
        relationship: relationship.trim() || null,
        witness: witness.trim(),
      }),
    onSuccess: (d) => {
      // Only the consent fields change; keep the typed note (the form isn't re-seeded).
      qc.setQueryData(['procedure', p.id], d)
      qc.invalidateQueries({ queryKey: ['procedures-worklist'] })
      toast(t('prc.consent_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Section title={t('prc.consent')}>
      {p.consent_signer ? (
        <ConsentSummary p={p} />
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-tx-3">{t('prc.consent_paper')}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Input
              label={t('prc.consent_signer')}
              placeholder={t('prc.consent_signer_ph')}
              value={signer}
              onChange={(e) => setSigner(e.target.value)}
            />
            <Input
              label={t('prc.consent_relationship')}
              placeholder={t('prc.consent_relationship_ph')}
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
            />
            <Input
              label={t('prc.consent_witness')}
              value={witness}
              onChange={(e) => setWitness(e.target.value)}
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            loading={record.isPending}
            disabled={!signer.trim() || !witness.trim()}
            onClick={() => record.mutate()}
          >
            <FileSignature className="h-4 w-4" />
            {t('prc.consent_record')}
          </Button>
        </div>
      )}
    </Section>
  )
}

function ConsentSummary({ p }: { p: Procedure }) {
  const t = useT()
  return (
    <div>
      <p className="flex items-center gap-1.5 text-sm text-tx">
        <CheckCircle2 className="h-4 w-4 text-ok" />
        {t('prc.consent_done')
          .replace(
            '{signer}',
            p.consent_relationship
              ? `${p.consent_signer} (${p.consent_relationship})`
              : (p.consent_signer ?? ''),
          )
          .replace('{witness}', p.consent_witness ?? '')}
      </p>
      <p className="mt-0.5 text-xs text-tx-3">
        {t('prc.consent_meta')
          .replace('{when}', fmtDateTimeTz(p.consent_at))
          .replace('{name}', p.consent_by_name ?? '—')}
      </p>
    </div>
  )
}

// ── read-only ────────────────────────────────────────────────────────────────────────────
function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-tx-3">{label}</dt>
      <dd className="whitespace-pre-wrap text-sm text-tx">{value ?? '—'}</dd>
    </div>
  )
}

const triLabel = (t: (k: string) => string, v: Tri) =>
  v === null ? t('prc.na') : v ? t('prc.yes') : t('prc.no')

function vitalsLine(t: (k: string) => string, p: Procedure, suffix: 'before' | 'after') {
  const parts = [
    p[`bp_${suffix}`] && `${t('prc.bp')} ${p[`bp_${suffix}`]}`,
    p[`hr_${suffix}`] !== null && `${t('prc.hr')} ${p[`hr_${suffix}`]}`,
    p[`spo2_${suffix}`] !== null && `SpO₂ ${p[`spo2_${suffix}`]} %`,
    p[`temp_${suffix}`] !== null && `${p[`temp_${suffix}`]} °C`,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

function ReadView({ p, allergies }: { p: Procedure; allergies: string[] }) {
  const t = useT()
  if (p.status === 'pending' && !p.started_at) return null
  return (
    <>
      <Section title={t('prc.before')}>
        <dl className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t('prc.allergies')}
            value={
              <>
                {allergies.length ? allergies.join(', ') : t('prc.no_allergies')}
                {p.allergies_reviewed && (
                  <span className="text-ok"> · {t('prc.allergies_reviewed')}</span>
                )}
              </>
            }
          />
          <Field
            label={`${t('prc.anticoagulants')} / ${t('prc.fasting')}`}
            value={`${triLabel(t, p.anticoagulants)} / ${triLabel(t, p.fasting)}`}
          />
          <Field label={t('prc.vitals_before')} value={vitalsLine(t, p, 'before')} />
          <Field label={t('prc.vitals_after')} value={vitalsLine(t, p, 'after')} />
        </dl>
      </Section>
      {p.requires_consent && (
        <Section title={t('prc.consent')}>
          {p.consent_signer ? (
            <ConsentSummary p={p} />
          ) : (
            <p className="text-sm text-tx-3">{t('prc.consent_missing')}</p>
          )}
        </Section>
      )}
      <Section title={t('prc.note')}>
        <dl className="space-y-3">
          <Field label={t('prc.anesthesia')} value={p.anesthesia} />
          {p.allergy_override && (
            <p className="flex items-center gap-1.5 text-[13px] text-warn">
              <AlertTriangle className="h-4 w-4" />
              {t('prc.allergy_noted').replace('{reason}', p.allergy_override)}
            </p>
          )}
          <Field label={t('prc.technique')} value={p.technique} />
          <Field label={t('prc.findings')} value={p.findings} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('prc.materials')} value={p.materials} />
            <Field label={t('prc.complications')} value={p.complications} />
          </div>
          <Field label={t('prc.instructions')} value={p.instructions} />
          <Field
            label={t('prc.specimen')}
            value={p.specimen_sent ? p.specimen_description : t('prc.no_specimen')}
          />
        </dl>
      </Section>
    </>
  )
}

function AmendModal({
  open,
  procedureId,
  onDone,
  onClose,
}: {
  open: boolean
  procedureId: string
  onDone: (d: ProcedureDetail) => void
  onClose: () => void
}) {
  const t = useT()
  const [text, setText] = useState('')
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) {
      setText('')
      setReason('')
    }
  }, [open])
  const amend = useMutation({
    mutationFn: () => proceduresApi.amend(procedureId, text.trim(), reason.trim()),
    onSuccess: onDone,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  return (
    <Modal open={open} onClose={onClose} title={t('prc.amend_title')}>
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          amend.mutate()
        }}
      >
        <p className="text-[13px] text-tx-3">{t('prc.amend_desc')}</p>
        <Textarea
          label={t('prc.amend_text')}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <Input
          label={t('prc.amend_reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={amend.isPending} disabled={!text.trim() || !reason.trim()}>
            {t('prc.amend')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

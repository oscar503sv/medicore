import type { ReactNode } from 'react'
import type {
  AgendaPrint,
  AppointmentPrint,
  CertificatePrint,
  PrintContext,
  ProcedureDocument,
  ProcedurePrint,
  RecordPrint,
} from '@/api/printing'
import type { ScheduledDose, VaccinationCard } from '@/api/vaccinations'
import { PatientStrip, PrintSheet, SignatureLine } from '@/components/print/PrintSheet'
import { VITAL_COLS, unitLabel } from '@/components/patients/vitalsData'
import { fmtDate, fmtDateTz, fmtTime, fmtTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { sectionTitle } from '@/lib/notes'
import { useFill } from '@/lib/printing'
import { doseLabel, vaccineName } from '@/lib/vaccination'
import type { ExamKind, PaperSize } from '@/types'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="print-avoid-break mt-4">
      <h2 className="mb-1 border-b border-neutral-300 pb-0.5 text-[9pt] font-semibold uppercase tracking-wide text-neutral-600">
        {title}
      </h2>
      <div className="text-[10pt]">{children}</div>
    </section>
  )
}

function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/\n+/)
        .filter((line) => line.trim())
        .map((line, i) => (
          <p key={i} className="mb-1">
            {line}
          </p>
        ))}
    </>
  )
}

// ── Prescription ──────────────────────────────────────────────────────────────

export function PrescriptionDoc({
  doc,
  paper,
  withIndications,
}: {
  doc: RecordPrint
  paper: PaperSize
  withIndications: boolean
}) {
  const t = useT()
  const LONG = t('pr.date_long')
  const f = useFill()
  const r = doc.record
  return (
    <PrintSheet
      ctx={doc.context}
      paper={paper}
      title={t('pr.doc.prescription')}
      code={r.code}
      doctorInHeader
      fillPage
      footer={<SignatureLine ctx={doc.context} />}
    >
      <PatientStrip ctx={doc.context} date={fmtDateTz(r.encounter_at, LONG)} showAllergies />
      <p className="mt-4 font-serif text-[16pt] italic leading-none">{t('pr.rx')}</p>
      <ol className="mt-2 space-y-2.5">
        {r.prescriptions.map((rx, i) => (
          <li key={i} className="print-avoid-break flex gap-2 text-[10.5pt]">
            <span className="w-4 shrink-0 text-neutral-500">{i + 1}.</span>
            <div>
              <p className="font-semibold">
                {rx.drug} <span className="font-normal">{rx.dose}</span>
              </p>
              <p>
                {rx.schedule}
                {rx.duration_days ? ` · ${f('pr.rx_days', { n: rx.duration_days })}` : ''}
                {!rx.duration_days && rx.end_date
                  ? ` · ${f('pr.rx_until', { v: fmtDate(rx.end_date, LONG) })}`
                  : ''}
              </p>
            </div>
          </li>
        ))}
      </ol>
      {withIndications && doc.indications && (
        <Section title={t('pr.indications')}>
          <Paragraphs text={doc.indications} />
        </Section>
      )}
    </PrintSheet>
  )
}

// ── Exam order ────────────────────────────────────────────────────────────────

const EXAM_ORDER: ExamKind[] = ['lab', 'imaging', 'other']

export function ExamOrderDoc({ doc, paper }: { doc: RecordPrint; paper: PaperSize }) {
  const t = useT()
  const LONG = t('pr.date_long')
  const r = doc.record
  return (
    <PrintSheet
      ctx={doc.context}
      paper={paper}
      title={t('pr.doc.exams')}
      code={r.code}
      doctorInHeader
      fillPage
      footer={<SignatureLine ctx={doc.context} />}
    >
      <PatientStrip ctx={doc.context} date={fmtDateTz(r.encounter_at, LONG)} />
      {EXAM_ORDER.map((kind) => {
        const exams = r.exams.filter((e) => e.kind === kind)
        if (exams.length === 0) return null
        return (
          <Section key={kind} title={t(`pr.exams.${kind}`)}>
            <ul className="space-y-1">
              {exams.map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-[0.45em] h-2 w-2 shrink-0 border border-neutral-700" />
                  <span>
                    <span className="font-semibold">{e.name}</span>
                    {e.notes && <span className="text-neutral-600"> — {e.notes}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </Section>
        )
      })}
      {r.diagnoses.length > 0 && (
        <Section title={t('pr.exams.indication')}>
          {r.diagnoses.map((d) => `${d.code} ${d.label}`).join('; ')}
        </Section>
      )}
    </PrintSheet>
  )
}

// ── Record copy ───────────────────────────────────────────────────────────────

export function RecordCopyDoc({ doc }: { doc: RecordPrint }) {
  const t = useT()
  const f = useFill()
  const r = doc.record
  const vitals = VITAL_COLS.filter((c) => r.vitals[c.key] != null)
  return (
    <PrintSheet
      ctx={doc.context}
      paper="letter"
      title={t('pr.doc.record')}
      code={r.code}
      footer={<SignatureLine ctx={doc.context} />}
    >
      <PatientStrip
        ctx={doc.context}
        date={fmtDateTz(r.encounter_at, 'd MMM yyyy HH:mm')}
        showAllergies
      />
      <p className="mt-1 text-[9pt] text-neutral-600">
        {r.code} · {r.location_name} · {t('pr.record.insurer')}:{' '}
        {r.insurer_name ?? t('pr.record.private')}
        {doc.amends_code && <> · {t('pr.record.amends')}</>}
      </p>
      <Section title={t('pr.record.reason')}>{r.chief_complaint}</Section>
      {vitals.length > 0 && (
        <Section title={t('consult.vitals')}>
          <div className="flex flex-wrap gap-x-5">
            {vitals.map((c) => (
              <span key={c.key}>
                <span className="text-neutral-500">{t(c.labelKey)}: </span>
                {String(r.vitals[c.key])} {unitLabel(t, c.unit)}
              </span>
            ))}
          </div>
        </Section>
      )}
      {r.note.sections.map((s) =>
        s.text.trim() ? (
          <Section key={s.key} title={sectionTitle(t, r.note.template, s)}>
            <Paragraphs text={s.text} />
          </Section>
        ) : null,
      )}
      {r.diagnoses.length > 0 && (
        <Section title={t('consult.diagnoses')}>
          <ul>
            {r.diagnoses.map((d) => (
              <li key={d.code}>
                <span className="font-mono">{d.code}</span> {d.label}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {r.prescriptions.length > 0 && (
        <Section title={t('consult.prescriptions')}>
          <ul>
            {r.prescriptions.map((rx, i) => (
              <li key={i}>
                <span className="font-semibold">{rx.drug}</span> {rx.dose} · {rx.schedule}
                {rx.duration_days ? ` · ${f('pr.rx_days', { n: rx.duration_days })}` : ''}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {r.exams.length > 0 && (
        <Section title={t('record.exams')}>
          <ul>
            {r.exams.map((e, i) => (
              <li key={i}>
                {e.name} <span className="text-neutral-500">({t(`exam.kind.${e.kind}`)})</span>
                {e.notes && ` — ${e.notes}`}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {r.vaccines.length > 0 && (
        <Section title={t('pr.record.vaccines')}>
          <ul>
            {r.vaccines.map((v, i) => (
              <li key={i}>
                {v.name} · {v.dose} · {v.lot} · {v.site}
              </li>
            ))}
          </ul>
        </Section>
      )}
      <p className="mt-4 text-[9pt] text-neutral-600">
        {f('pr.record.signed', { v: fmtDateTz(r.signed_at, 'd MMM yyyy HH:mm') })}
      </p>
    </PrintSheet>
  )
}

// ── Medical certificate ───────────────────────────────────────────────────────

export function CertificateDoc({ doc, paper }: { doc: CertificatePrint; paper: PaperSize }) {
  const t = useT()
  const LONG = t('pr.date_long')
  const f = useFill()
  const c = doc.certificate
  const p = doc.context.patient
  const doctorSex = doc.context.doctor?.sex === 'female' ? 'female' : 'male'
  const patientSex = p?.sex === 'female' || p?.sex === 'male' ? p.sex : 'other'
  const base = {
    undersigned: t(`pr.cert.undersigned_${doctorSex}`),
    seen: t(`pr.cert.seen_${patientSex}`),
    patient: p?.name ?? '',
    age: p?.age ?? '',
    date: fmtDateTz(doc.encounter_at, LONG),
  }
  const body =
    c.kind === 'attendance'
      ? f('pr.cert.attendance', {
          ...base,
          from: fmtTimeTz(doc.encounter_at),
          to: fmtTimeTz(doc.ended_at),
        })
      : f(c.rest_days === 1 ? 'pr.cert.rest_one' : 'pr.cert.rest', {
          ...base,
          days: c.rest_days ?? 0,
          from: fmtDate(c.rest_from, LONG),
          to: fmtDate(c.rest_until, LONG),
        })
  return (
    <PrintSheet
      ctx={doc.context}
      paper={paper}
      title={t('pr.doc.certificate')}
      code={c.code}
      doctorInHeader
      fillPage
      footer={<SignatureLine ctx={doc.context} />}
    >
      <div className="mt-6 space-y-3 text-justify text-[11pt]">
        <p className="font-semibold">
          {c.addressee ? `${c.addressee}:` : t('pr.cert.addressee_default')}
        </p>
        <p>{body}</p>
        {c.diagnosis && <p>{f('pr.cert.diagnosis', { v: c.diagnosis })}</p>}
        {c.remarks && <Paragraphs text={c.remarks} />}
        <p>
          {f('pr.cert.closing', {
            place: doc.context.clinic.location_name,
            date: fmtDateTz(c.issued_at, LONG),
          })}
        </p>
      </div>
    </PrintSheet>
  )
}

// ── Procedures ────────────────────────────────────────────────────────────────

export function ProcedureDoc({
  doc,
  document,
  paper,
}: {
  doc: ProcedurePrint
  document: ProcedureDocument
  paper: PaperSize
}) {
  const t = useT()
  const LONG = t('pr.date_long')
  const f = useFill()
  const p = doc.procedure
  const ctx = doc.context
  const date = p.performed_at ? fmtDateTz(p.performed_at, LONG) : fmtDate(ctx.printed_at, LONG)

  if (document === 'consent') {
    const sex = ctx.doctor?.sex === 'female' ? 'female' : 'male'
    return (
      <PrintSheet ctx={ctx} paper="letter" title={t('pr.doc.consent')}>
        <PatientStrip ctx={ctx} date={fmtDate(ctx.printed_at, LONG)} showAllergies />
        <div className="mt-4 space-y-3 text-justify text-[10.5pt]">
          <p>
            {f('pr.consent.body', {
              who: t('pr.consent.who'),
              the_doctor: t(`pr.consent.the_doctor_${sex}`),
              doctor: ctx.doctor?.name ?? '________________',
              procedure: p.type_name,
              indication: p.indication,
            })}
          </p>
          <p>{t('pr.consent.items')}</p>
          <div>
            <p className="font-semibold">{t('pr.consent.risks')}</p>
            {[0, 1, 2].map((i) => (
              <div key={i} className="mt-5 border-b border-neutral-400" />
            ))}
          </div>
          <p className="font-semibold">{t('pr.consent.agree')}</p>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-x-10">
          <SignatureLine label={t('pr.consent.patient_sign')} />
          <SignatureLine label={t('pr.consent.relationship')} />
          <SignatureLine label={t('pr.consent.witness_sign')} />
          <SignatureLine label={t(`pr.consent.doctor_sign_${sex}`)} ctx={ctx} />
        </div>
      </PrintSheet>
    )
  }

  if (document === 'pathology') {
    return (
      <PrintSheet
        ctx={ctx}
        paper="letter"
        title={t('pr.doc.pathology')}
        doctorInHeader
        footer={<SignatureLine ctx={ctx} />}
      >
        <PatientStrip ctx={ctx} date={date} />
        <Section title={t('pr.path.procedure')}>
          {p.type_name}
          {p.performed_at && ` · ${t('pr.path.date')}: ${date}`}
        </Section>
        <Section title={t('pr.path.specimen')}>{p.specimen_description || '—'}</Section>
        <Section title={t('pr.path.clinical')}>
          <Paragraphs text={p.indication} />
        </Section>
        {p.findings && (
          <Section title={t('pr.path.findings')}>
            <Paragraphs text={p.findings} />
          </Section>
        )}
      </PrintSheet>
    )
  }

  return (
    <PrintSheet
      ctx={ctx}
      paper={paper}
      title={t('pr.doc.instructions')}
      doctorInHeader
      fillPage
      footer={<SignatureLine ctx={ctx} />}
    >
      <PatientStrip ctx={ctx} date={date} />
      <p className="mt-3 text-[10.5pt] font-semibold">{p.type_name}</p>
      <Section title={t('pr.indications')}>
        <Paragraphs text={p.instructions ?? ''} />
      </Section>
      {(p.follow_up_on || p.follow_up_days) && (
        <p className="mt-3 text-[10.5pt] font-semibold">
          {p.follow_up_on
            ? f('pr.proc.follow_up', { v: fmtDate(p.follow_up_on, LONG) })
            : f('pr.proc.follow_up_days', { n: p.follow_up_days ?? 0 })}
        </p>
      )}
    </PrintSheet>
  )
}

// ── Vaccination card ──────────────────────────────────────────────────────────

export function VaccinationCardDoc({
  ctx,
  card,
  doses,
}: {
  ctx: PrintContext
  card: VaccinationCard
  doses: ScheduledDose[]
}) {
  const t = useT()
  const LONG = t('pr.date_long')
  const byKey = new Map(doses.map((d) => [d.key, d]))
  const applied = card.records
    .filter((r) => !r.voided_at && r.outcome === 'administered')
    .sort((a, b) => a.occurred_on.localeCompare(b.occurred_on))
  const pending = card.states
    .filter((s) => ['overdue', 'due', 'due_soon'].includes(s.status) && s.due_on)
    .sort((a, b) => (a.due_on ?? '').localeCompare(b.due_on ?? ''))
  const dose = (key: string | null) => {
    const d = key ? byKey.get(key) : undefined
    return d ? doseLabel(t, d) : '—'
  }
  return (
    <PrintSheet ctx={ctx} paper="letter" title={t('pr.doc.vaccination_card')}>
      <PatientStrip ctx={ctx} date={fmtDate(ctx.printed_at, LONG)} />
      <Section title={t('pr.vax.applied')}>
        {applied.length === 0 ? (
          <p className="text-neutral-500">{t('pr.vax.none')}</p>
        ) : (
          <table className="w-full text-left text-[9.5pt]">
            <thead className="text-neutral-500">
              <tr>
                <th className="py-0.5 font-normal">{t('pr.vax.vaccine')}</th>
                <th className="font-normal">{t('pr.vax.dose')}</th>
                <th className="font-normal">{t('pr.vax.date')}</th>
                <th className="font-normal">{t('pr.vax.lot')}</th>
                <th className="font-normal">{t('pr.vax.where')}</th>
              </tr>
            </thead>
            <tbody>
              {applied.map((r) => (
                <tr key={r.id} className="border-t border-neutral-200">
                  <td className="py-0.5">{vaccineName(t, r.vaccine_code)}</td>
                  <td>{dose(r.dose_key)}</td>
                  <td>{fmtDate(r.occurred_on)}</td>
                  <td>{r.lot ?? '—'}</td>
                  <td>{t(r.source === 'clinic' ? 'pr.vax.clinic' : 'pr.vax.external')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
      {pending.length > 0 && (
        <Section title={t('pr.vax.pending')}>
          <table className="w-full text-left text-[9.5pt]">
            <thead className="text-neutral-500">
              <tr>
                <th className="py-0.5 font-normal">{t('pr.vax.vaccine')}</th>
                <th className="font-normal">{t('pr.vax.dose')}</th>
                <th className="font-normal">{t('pr.vax.due')}</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((s) => (
                <tr key={s.key} className="border-t border-neutral-200">
                  <td className="py-0.5">{vaccineName(t, byKey.get(s.key)?.vaccine ?? s.key)}</td>
                  <td>{dose(s.key)}</td>
                  <td>{fmtDate(s.due_on)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </PrintSheet>
  )
}

// ── Appointment slip ──────────────────────────────────────────────────────────

export function AppointmentSlipDoc({ doc, paper }: { doc: AppointmentPrint; paper: PaperSize }) {
  const t = useT()
  const f = useFill()
  const a = doc.appointment
  const { clinic, doctor, patient } = doc.context
  const rows: [string, ReactNode][] = [
    [t('pr.patient'), `${patient?.name ?? ''} · ${patient?.code ?? ''}`],
    [
      t('pr.appt.when'),
      <span key="w" className="font-semibold">
        {`${fmtDate(a.scheduled_start, t('pr.date_weekday'))} · ${fmtTime(a.scheduled_start)}`}
      </span>,
    ],
    [
      t('pr.appt.with'),
      `${doctor?.name ?? ''}${doctor?.specialty ? ` · ${doctor.specialty}` : ''}`,
    ],
    [
      t('pr.appt.type'),
      `${t(`apptype.${a.type}`)} · ${f('pr.appt.duration', { n: a.duration_minutes })}`,
    ],
    [
      t('pr.appt.where'),
      [clinic.location_name, clinic.address, clinic.phone].filter(Boolean).join(' · '),
    ],
  ]
  return (
    <PrintSheet ctx={doc.context} paper={paper} title={t('pr.doc.appointment')} code={a.code}>
      <dl className="mt-4 space-y-2 text-[10.5pt]">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-[8.5pt] uppercase tracking-wide text-neutral-500">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-5 border-t border-neutral-300 pt-2 text-[9pt] text-neutral-600">
        {t('pr.appt.note')}
      </p>
    </PrintSheet>
  )
}

// ── Day's agenda ──────────────────────────────────────────────────────────────

export function AgendaDoc({ doc }: { doc: AgendaPrint }) {
  const t = useT()
  const f = useFill()
  const doctor = doc.context.doctor
  return (
    <PrintSheet ctx={doc.context} paper="letter" title={t('pr.doc.agenda')}>
      <p className="mt-2 text-center text-[10pt]">
        <span className="font-semibold">{doctor?.name}</span> ·{' '}
        {fmtDate(doc.day, t('pr.date_weekday'))}
        {' · '}
        {f('pr.agenda.total', { n: doc.rows.length })}
      </p>
      {doc.rows.length === 0 ? (
        <p className="mt-6 text-center text-neutral-500">{t('pr.agenda.empty')}</p>
      ) : (
        <table className="mt-4 w-full text-left text-[9.5pt]">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-1 font-normal">{t('pr.agenda.time')}</th>
              <th className="font-normal">{t('pr.agenda.patient')}</th>
              <th className="font-normal">{t('pr.agenda.type')}</th>
              <th className="font-normal">{t('pr.agenda.reason')}</th>
              <th className="font-normal">{t('pr.agenda.status')}</th>
            </tr>
          </thead>
          <tbody>
            {doc.rows.map((r) => (
              <tr key={r.code} className="print-avoid-break border-t border-neutral-200 align-top">
                <td className="py-1 font-mono">{fmtTime(r.scheduled_start)}</td>
                <td>
                  {r.patient_name} <span className="text-neutral-500">{r.patient_code}</span>
                </td>
                <td>{t(`apptype.${r.type}`)}</td>
                <td>{r.reason}</td>
                <td>{t(`status.${r.status}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </PrintSheet>
  )
}

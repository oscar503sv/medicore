import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Circle, Pill, Stethoscope, Tag } from 'lucide-react'
import { prescriptionsApi } from '@/api/prescriptions'
import { recordsApi } from '@/api/records'
import { RecordDrawer } from '@/components/records/RecordDrawer'
import { fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Patient } from '@/types'

const MAX_RX = 5

export interface RailSection {
  id: string // element id to scroll to
  label: string
  done?: boolean
  optional?: boolean // not needed to sign: shown without a check
  count?: number
}

/**
 * The consultation's right rail: how complete the note is, the sections with what is
 * still missing (each one jumps to its section), and the patient's context the doctor
 * needs while writing: conditions, active medication and previous visits.
 */
export function ConsultationRail({
  completion,
  sections,
  patient,
  consultationId,
}: {
  completion: number
  sections: RailSection[]
  patient: Patient | null
  consultationId: string
}) {
  const t = useT()
  return (
    <aside className="space-y-4 lg:sticky lg:top-0 lg:self-start">
      <div className="rounded-lg border border-line bg-surface p-4">
        <div className="flex items-center gap-4">
          <CompletionRing percent={completion} />
          <div>
            <p className="text-[13px] font-medium text-tx">{t('consult.completion')}</p>
            <p className="text-xs text-tx-3">
              {sections.every((s) => s.optional || s.done)
                ? t('consult.ready')
                : t('consult.to_sign')}
            </p>
          </div>
        </div>
        <nav aria-label={t('consult.sections')} className="mt-3 space-y-0.5">
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() =>
                document
                  .getElementById(s.id)
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] text-tx-2 hover:bg-surface-2"
            >
              {s.optional ? (
                <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                  <span className="h-1.5 w-1.5 rounded-pill bg-tx-4" />
                </span>
              ) : s.done ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" />
              ) : (
                <Circle className="h-4 w-4 shrink-0 text-tx-4" />
              )}
              <span className="flex-1">{s.label}</span>
              {s.count != null && s.count > 0 && (
                <span className="text-xs text-tx-4">{s.count}</span>
              )}
            </button>
          ))}
        </nav>
      </div>
      {patient && <PatientContext patient={patient} consultationId={consultationId} />}
    </aside>
  )
}

function PatientContext({ patient, consultationId }: { patient: Patient; consultationId: string }) {
  const t = useT()
  const [openRecord, setOpenRecord] = useState<string | null>(null)
  const { data: prescriptions = [] } = useQuery({
    queryKey: ['prescriptions', patient.id],
    queryFn: () => prescriptionsApi.list(patient.id),
  })
  const { data: records } = useQuery({
    queryKey: ['records', { patient_id: patient.id }],
    queryFn: () => recordsApi.list({ patient_id: patient.id }),
  })
  // Each medication once (repeat prescriptions of the same drug and dose), the first few.
  const active = [
    ...new Map(
      prescriptions.filter((p) => p.status === 'active').map((p) => [`${p.drug}|${p.dose}`, p]),
    ).values(),
  ]
  const shown = active.slice(0, MAX_RX)
  // Signed visits only, newest first; this consultation has no record yet.
  const visits = (records ?? [])
    .filter((r) => r.consultation_id !== consultationId)
    .sort((a, b) => b.encounter_at.localeCompare(a.encounter_at))
    .slice(0, 4)

  return (
    <div className="space-y-4 rounded-lg border border-line bg-surface p-4">
      <ContextBlock icon={<Tag className="h-3.5 w-3.5" />} title={t('consult.conditions')}>
        {patient.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {patient.tags.map((tag) => (
              <span key={tag} className="rounded-pill bg-surface-2 px-2 py-0.5 text-xs text-tx-2">
                {tag}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-tx-4">{t('consult.no_conditions')}</p>
        )}
      </ContextBlock>
      <ContextBlock icon={<Pill className="h-3.5 w-3.5" />} title={t('consult.active_rx')}>
        {active.length > 0 ? (
          <ul className="space-y-1">
            {shown.map((p) => (
              <li key={p.id} className="text-xs text-tx-2">
                <span className="font-medium text-tx">{p.drug}</span> · {p.dose} · {p.schedule}
              </li>
            ))}
            {active.length > MAX_RX && (
              <li className="text-xs text-tx-4">
                {t('consult.more').replace('{n}', String(active.length - MAX_RX))}
              </li>
            )}
          </ul>
        ) : (
          <p className="text-xs text-tx-4">{t('consult.no_active_rx')}</p>
        )}
      </ContextBlock>
      <ContextBlock icon={<Stethoscope className="h-3.5 w-3.5" />} title={t('consult.last_visits')}>
        {records && visits.length === 0 ? (
          <p className="text-xs text-tx-4">{t('consult.first_visit')}</p>
        ) : (
          <ul className="space-y-1">
            {visits.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setOpenRecord(r.id)}
                  className="w-full rounded-md px-1.5 py-1 text-left hover:bg-surface-2"
                >
                  <span className="block text-xs text-tx-3">{fmtDateTz(r.encounter_at)}</span>
                  <span className="block truncate text-xs text-tx">
                    {r.diagnoses[0]?.label ?? r.chief_complaint}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </ContextBlock>
      <RecordDrawer recordId={openRecord} onClose={() => setOpenRecord(null)} />
    </div>
  )
}

function ContextBlock({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <div>
      <p className="eyebrow mb-1.5 flex items-center gap-1.5 text-tx-3">
        {icon}
        {title}
      </p>
      {children}
    </div>
  )
}

function CompletionRing({ percent }: { percent: number }) {
  const r = 40
  const c = 2 * Math.PI * r
  const offset = c - (percent / 100) * c
  return (
    <svg viewBox="0 0 100 100" className="h-16 w-16 shrink-0" role="img" aria-label={`${percent}%`}>
      <circle cx="50" cy="50" r={r} fill="none" stroke="var(--line)" strokeWidth="9" />
      <circle
        cx="50"
        cy="50"
        r={r}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform="rotate(-90 50 50)"
        style={{ transition: 'stroke-dashoffset .4s ease' }}
      />
      <text x="50" y="58" textAnchor="middle" className="fill-tx font-serif text-[26px]">
        {percent}%
      </text>
    </svg>
  )
}

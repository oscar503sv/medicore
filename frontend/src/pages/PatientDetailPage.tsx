import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Pencil } from 'lucide-react'
import { Link } from 'react-router-dom'
import { insurersApi } from '@/api/insurers'
import { patientsApi } from '@/api/patients'
import { recordsApi } from '@/api/records'
import { EditPatientModal } from '@/components/patients/EditPatientModal'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { useAuthStore } from '@/stores/auth'
import { cn } from '@/lib/cn'
import { fmtDate, fmtDateTime } from '@/lib/format'
import { useT } from '@/lib/i18n'

type Tab = 'summary' | 'history' | 'prescriptions' | 'vitals' | 'documents'

export function PatientDetailPage() {
  const t = useT()
  const { id = '' } = useParams()
  const [tab, setTab] = useState<Tab>('summary')
  const [editOpen, setEditOpen] = useState(false)
  const canEdit = useAuthStore((s) => s.hasRole('admin', 'doctor', 'receptionist'))

  const { data, isLoading } = useQuery({
    queryKey: ['patient', id],
    queryFn: () => patientsApi.get(id),
  })
  const { data: insurers } = useQuery({
    queryKey: ['insurers'],
    queryFn: () => insurersApi.list(),
  })
  const { data: records } = useQuery({
    queryKey: ['records', { patient_id: id }],
    queryFn: () => recordsApi.list({ patient_id: id }),
    enabled: tab === 'history',
  })

  if (isLoading || !data) return <PageLoader />
  const p = data.patient
  const insurerName = insurers?.find((i) => i.id === p.insurance_id)?.name ?? null

  const tabs: { id: Tab; label: string }[] = [
    { id: 'summary', label: t('patient.summary') },
    { id: 'history', label: t('patient.history') },
    { id: 'prescriptions', label: t('patient.prescriptions') },
    { id: 'vitals', label: t('patient.vitals') },
    { id: 'documents', label: t('patient.documents') },
  ]

  return (
    <div className="space-y-6 p-8">
      <Link to="/patients" className="inline-flex items-center gap-1.5 text-[13px] text-tx-3 hover:text-tx">
        <ArrowLeft className="h-4 w-4" />
        {t('nav.patients')}
      </Link>

      {/* Header */}
      <div className="flex items-start gap-5">
        <Avatar name={`${p.first_name} ${p.last_name}`} size="lg" />
        <div className="flex-1">
          <h1 className="font-serif text-3xl text-tx">
            {p.first_name} {p.last_name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-tx-3">
            <span className="font-mono">{p.code}</span>
            <span>{p.age} años</span>
            <span>{p.sex === 'male' ? 'Masculino' : p.sex === 'female' ? 'Femenino' : 'Otro'}</span>
            {p.blood_type && <span>Grupo {p.blood_type}</span>}
            {insurerName && <span>{insurerName}</span>}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {p.tags.map((tag) => (
              <Badge key={tag} tone="accent">
                {tag}
              </Badge>
            ))}
            {p.allergies.map((a) => (
              <Badge key={a} tone="danger">
                ⚠ {a}
              </Badge>
            ))}
          </div>
        </div>
        {canEdit && (
          <Button variant="outline" onClick={() => setEditOpen(true)}>
            <Pencil className="h-4 w-4" />
            {t('app.edit')}
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-line">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
              tab === tb.id
                ? 'border-accent text-accent'
                : 'border-transparent text-tx-3 hover:text-tx',
            )}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === 'summary' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <div className="space-y-4">
            <Card>
              <CardHeader title={t('patient.contact')} />
              <dl className="space-y-2 p-5 text-sm">
                <Row label="Teléfono" value={p.contact.phone} />
                <Row label="Email" value={p.contact.email} />
                <Row label="Dirección" value={p.contact.address} />
                <Row label="Contacto emergencia" value={p.contact.emergency_contact_name} />
                <Row label={t('patientform.insurer')} value={insurerName} />
              </dl>
            </Card>
          </div>
          <div className="space-y-4">
            <Card className="p-5">
              <div className="grid grid-cols-2 gap-4">
                <Metric label={t('patients.col_last')} value={fmtDateTime(data.last_visit)} />
                <Metric label={t('patients.col_next')} value={fmtDateTime(data.next_visit)} />
                <Metric label="Historiales" value={String(data.records_count)} />
                <Metric label="Recetas activas" value={String(data.active_prescriptions)} />
              </div>
            </Card>
          </div>
        </div>
      )}

      {tab === 'history' && (
        <Card>
          <div className="divide-y divide-line-soft">
            {(records ?? []).map((r) => (
              <div key={r.id} className="px-5 py-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-tx">{r.chief_complaint}</p>
                  <Badge tone={r.status === 'amended' ? 'info' : 'ok'}>
                    {t(`records.${r.status === 'amended' ? 'amended' : 'signed'}`)}
                  </Badge>
                </div>
                <p className="mt-1 font-mono text-xs text-tx-3">
                  {r.code} · {fmtDate(r.encounter_at)}
                </p>
              </div>
            ))}
            {(!records || records.length === 0) && (
              <p className="px-5 py-8 text-center text-sm text-tx-3">Sin historiales</p>
            )}
          </div>
        </Card>
      )}

      {(tab === 'prescriptions' || tab === 'vitals' || tab === 'documents') && (
        <Card className="p-8 text-center text-sm text-tx-3">
          Sección en desarrollo
        </Card>
      )}

      <EditPatientModal patient={editOpen ? p : null} onClose={() => setEditOpen(false)} />
    </div>
  )
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-tx-3">{label}</dt>
      <dd className="text-right text-tx">{value || '—'}</dd>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="text-sm font-medium text-tx">{value}</p>
    </div>
  )
}

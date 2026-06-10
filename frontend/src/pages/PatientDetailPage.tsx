import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArrowLeft, Lock, Pencil, RotateCcw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { recordsApi } from '@/api/records'
import { EditPatientModal } from '@/components/patients/EditPatientModal'
import { MedicationTimeline } from '@/components/patients/MedicationTimeline'
import { PatientDocuments } from '@/components/patients/PatientDocuments'
import { PatientSummary } from '@/components/patients/PatientSummary'
import { VitalsHistory } from '@/components/patients/VitalsHistory'
import { RecordDrawer } from '@/components/records/RecordDrawer'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { useAuthStore } from '@/stores/auth'
import { cn } from '@/lib/cn'
import { fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'

type Tab = 'summary' | 'history' | 'prescriptions' | 'vitals' | 'documents'

export function PatientDetailPage() {
  const t = useT()
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('summary')
  const [editOpen, setEditOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [openRecordId, setOpenRecordId] = useState<string | null>(null)
  const canEdit = useAuthStore((s) => s.can('patients.edit'))
  const canArchive = useAuthStore((s) => s.can('patients.archive'))
  // History is visible to everyone but only a doctor may open it (clinical authorship,
  // not a grantable capability); the clinical tabs follow records.view.
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const canClinical = useAuthStore((s) => s.can('records.view'))

  const { data, isLoading } = useQuery({
    queryKey: ['patient', id],
    queryFn: () => patientsApi.get(id),
  })
  const { data: records } = useQuery({
    queryKey: ['records', { patient_id: id }],
    queryFn: () => recordsApi.list({ patient_id: id }),
    enabled:
      tab === 'history' ||
      tab === 'prescriptions' ||
      tab === 'vitals' ||
      (tab === 'summary' && canClinical),
  })

  const archivePatient = useMutation({
    mutationFn: () => patientsApi.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', id] })
      qc.invalidateQueries({ queryKey: ['patients'] })
      setArchiveOpen(false)
      toast(t('patient.archived_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  // Reactivation is safe and reversible, so no confirmation modal (unlike archiving).
  const reactivatePatient = useMutation({
    mutationFn: () => patientsApi.reactivate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', id] })
      qc.invalidateQueries({ queryKey: ['patients'] })
      toast(t('patient.reactivated_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !data) return <PageLoader />
  const p = data.patient

  const tabs: { id: Tab; label: string; locked?: boolean }[] = [
    { id: 'summary', label: t('patient.summary') },
    { id: 'history', label: t('patient.history'), locked: !isDoctor },
    ...(canClinical
      ? ([
          { id: 'prescriptions', label: t('patient.prescriptions') },
          { id: 'vitals', label: t('patient.vitals') },
          { id: 'documents', label: t('patient.documents') },
        ] as const)
      : []),
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
            {p.status === 'inactive' && <Badge tone="neutral">{t('patients.inactive')}</Badge>}
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
        <div className="flex gap-2">
          {canEdit && (
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4" />
              {t('app.edit')}
            </Button>
          )}
          {canArchive && p.status === 'active' && (
            <Button variant="outline" onClick={() => setArchiveOpen(true)}>
              <Archive className="h-4 w-4" />
              {t('patient.archive')}
            </Button>
          )}
          {canArchive && p.status === 'inactive' && (
            <Button
              variant="outline"
              loading={reactivatePatient.isPending}
              onClick={() => reactivatePatient.mutate()}
            >
              <RotateCcw className="h-4 w-4" />
              {t('patient.reactivate')}
            </Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-line">
        {tabs.map((tb) =>
          tb.locked ? (
            <span
              key={tb.id}
              title={t('patient.history_locked')}
              className="-mb-px inline-flex cursor-not-allowed items-center gap-1.5 border-b-2 border-transparent px-4 py-2.5 text-[13px] font-medium text-tx-4"
            >
              {tb.label}
              <Lock className="h-3 w-3" />
            </span>
          ) : (
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
          ),
        )}
      </div>

      {/* Content */}
      {tab === 'summary' && <PatientSummary detail={data} records={records ?? []} />}

      {tab === 'history' && (
        <Card>
          <div className="divide-y divide-line-soft">
            {(records ?? []).map((r) => (
              <button
                key={r.id}
                onClick={() => setOpenRecordId(r.id)}
                className="block w-full px-5 py-4 text-left transition-colors hover:bg-surface-2"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-tx">{r.chief_complaint}</p>
                  <Badge tone={r.status === 'amended' ? 'info' : 'ok'}>
                    {t(`records.${r.status === 'amended' ? 'amended' : 'signed'}`)}
                  </Badge>
                </div>
                <p className="mt-1 font-mono text-xs text-tx-3">
                  {r.code} · {fmtDateTz(r.encounter_at)}
                </p>
              </button>
            ))}
            {(!records || records.length === 0) && (
              <p className="px-5 py-8 text-center text-sm text-tx-3">{t('patient.history_empty')}</p>
            )}
          </div>
        </Card>
      )}

      {tab === 'prescriptions' && <MedicationTimeline records={records ?? []} />}

      {tab === 'vitals' && <VitalsHistory records={records ?? []} />}

      {tab === 'documents' && <PatientDocuments patientId={id} />}

      <EditPatientModal patient={editOpen ? p : null} onClose={() => setEditOpen(false)} />
      <RecordDrawer recordId={openRecordId} onClose={() => setOpenRecordId(null)} />

      <Modal
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        title={t('patient.archive_title')}
        width="max-w-md"
      >
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('patient.archive_confirm')}</p>
          <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
            <p className="font-medium text-tx">
              {p.first_name} {p.last_name}
            </p>
            <p className="font-mono text-xs text-tx-3">{p.code}</p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setArchiveOpen(false)}>
              {t('app.back')}
            </Button>
            <Button
              variant="danger"
              loading={archivePatient.isPending}
              onClick={() => archivePatient.mutate()}
            >
              {t('patient.archive')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

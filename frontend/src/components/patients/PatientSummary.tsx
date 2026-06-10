import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, MapPin, Phone, ShieldAlert, Stethoscope, type LucideIcon } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { RescheduleAppointmentModal } from '@/components/appointments/RescheduleAppointmentModal'
import { RecordDrawer } from '@/components/records/RecordDrawer'
import { VitalStat } from '@/components/patients/VitalsHistory'
import { VITAL_COLS, hasAnyVital } from '@/components/patients/vitalsData'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useAuthStore } from '@/stores/auth'
import { fmtDate, fmtDateTime, fmtDateTz, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { MedicalRecord, PatientDetail } from '@/types'

export function PatientSummary({
  detail,
  records,
}: {
  detail: PatientDetail
  records: MedicalRecord[]
}) {
  const t = useT()
  const qc = useQueryClient()
  const canClinical = useAuthStore((s) => s.can('records.view'))
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const canManage = useAuthStore((s) => s.can('appointments.manage'))

  const [rescheduleOpen, setRescheduleOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [openRecordId, setOpenRecordId] = useState<string | null>(null)

  const p = detail.patient
  const c = p.contact
  const appt = detail.next_appointment

  const refreshPatient = () => qc.invalidateQueries({ queryKey: ['patient', p.id] })

  const cancel = useMutation({
    mutationFn: () => appointmentsApi.cancel(appt!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      refreshPatient()
      setCancelOpen(false)
      toast(t('appt.cancelled_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const emergency = [c.emergency_contact_name, c.emergency_contact_phone].filter(Boolean).join(' · ')

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
      {/* ── Sidebar ────────────────────────────────────────────────── */}
      <div className="space-y-4">
        {/* Contact */}
        <Card>
          <CardHeader title={t('patient.contact')} />
          <dl className="space-y-3.5 p-5 text-sm">
            <ContactRow icon={Phone} label={t('patientform.phone')} value={c.phone} />
            <ContactRow icon={Mail} label={t('patientform.email')} value={c.email} />
            <ContactRow icon={MapPin} label={t('patientform.address')} value={c.address} />
            <ContactRow icon={ShieldAlert} label={t('patient.emergency')} value={emergency || null} />
          </dl>
        </Card>

        {/* Latest vitals (clinical roles only) */}
        {canClinical && <LatestVitalsCard records={records} />}

        {/* Next appointment */}
        <Card>
          <CardHeader title={t('patient.next_appt')} />
          {appt ? (
            <div className="space-y-3 p-5">
              <div>
                <p className="font-serif text-2xl leading-tight text-tx first-letter:uppercase">
                  {fmtDate(appt.scheduled_start, "EEEE d 'de' MMMM")}
                </p>
                <p className="mt-0.5 text-sm text-tx-3">
                  {fmtTime(appt.scheduled_start)} · {appt.duration_minutes} min
                </p>
              </div>
              <p className="text-sm text-tx">{appt.reason}</p>
              <p className="flex items-center gap-1.5 text-[13px] text-tx-3">
                <Stethoscope className="h-3.5 w-3.5" />
                {[appt.doctor_name, appt.room].filter(Boolean).join(' · ') || '—'}
              </p>
              <Badge tone={appt.status === 'confirmed' ? 'ok' : 'info'}>
                {t(`status.${appt.status}`)}
              </Badge>
              {canManage && (
                <div className="flex gap-2 pt-1">
                  <Button size="sm" variant="outline" onClick={() => setRescheduleOpen(true)}>
                    {t('appt.reschedule')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setCancelOpen(true)}>
                    {t('app.cancel')}
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <p className="px-5 py-8 text-center text-sm text-tx-3">{t('patient.no_next_appt')}</p>
          )}
        </Card>
      </div>

      {/* ── Main content ───────────────────────────────────────────── */}
      <div className="space-y-4">
        <Card className="p-5">
          <div className="grid grid-cols-3 gap-4">
            <Metric label={t('patients.col_last')} value={fmtDateTime(detail.last_visit)} />
            <Metric label={t('patient.records_count')} value={String(detail.records_count)} />
            <Metric label={t('patient.active_rx')} value={String(detail.active_prescriptions)} />
          </div>
        </Card>

        {canClinical && (
          <Card>
            <CardHeader title={t('patient.recent_activity')} />
            <RecentActivity
              records={records}
              onOpen={isDoctor ? setOpenRecordId : undefined}
            />
          </Card>
        )}
      </div>

      {/* Modals / drawer */}
      <RescheduleAppointmentModal
        appointment={rescheduleOpen ? appt : null}
        onClose={() => {
          setRescheduleOpen(false)
          refreshPatient()
        }}
      />
      <Modal open={cancelOpen} onClose={() => setCancelOpen(false)} title={t('appt.cancel_title')} width="max-w-md">
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('appt.cancel_confirm')}</p>
          {appt && (
            <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
              <p className="font-medium text-tx">{fmtDate(appt.scheduled_start, "d MMM · ")}{fmtTime(appt.scheduled_start)}</p>
              <p className="text-tx-3">{appt.reason}</p>
            </div>
          )}
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button variant="outline" onClick={() => setCancelOpen(false)}>
              {t('app.back')}
            </Button>
            <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              {t('appt.cancel_appt')}
            </Button>
          </div>
        </div>
      </Modal>
      <RecordDrawer recordId={openRecordId} onClose={() => setOpenRecordId(null)} />
    </div>
  )
}

function ContactRow({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string | null }) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-tx-3" />
      <div className="min-w-0">
        <dt className="eyebrow">{label}</dt>
        <dd className="break-words text-tx">{value || '—'}</dd>
      </div>
    </div>
  )
}

function LatestVitalsCard({ records }: { records: MedicalRecord[] }) {
  const t = useT()
  const latest = records
    .filter((r) => hasAnyVital(r.vitals))
    .sort((a, b) => b.encounter_at.localeCompare(a.encounter_at))[0]

  return (
    <Card>
      <CardHeader title={t('patient.vitals')} />
      {latest ? (
        <div className="p-5">
          <p className="eyebrow mb-2.5">{fmtDateTz(latest.encounter_at)}</p>
          <div className="grid grid-cols-2 gap-2.5">
            {VITAL_COLS.filter((col) => latest.vitals[col.key] != null).map((col) => (
              <VitalStat key={col.key} col={col} value={latest.vitals[col.key]!} />
            ))}
          </div>
        </div>
      ) : (
        <p className="px-5 py-8 text-center text-sm text-tx-3">{t('patient.vitals_empty')}</p>
      )}
    </Card>
  )
}

function RecentActivity({
  records,
  onOpen,
}: {
  records: MedicalRecord[]
  onOpen?: (id: string) => void
}) {
  const t = useT()
  const items = [...records]
    .sort((a, b) => b.encounter_at.localeCompare(a.encounter_at))
    .slice(0, 6)

  if (items.length === 0)
    return <p className="px-5 py-8 text-center text-sm text-tx-3">{t('patient.history_empty')}</p>

  return (
    <div className="relative py-5 pl-12 pr-5">
      <div className="absolute bottom-6 left-[26px] top-6 w-px bg-line" />
      <div className="space-y-5">
        {items.map((r) => {
          const body = (
            <>
              <p className="text-[13px] text-tx-3">{fmtDateTz(r.encounter_at, "d MMM yyyy · HH:mm")}</p>
              <p className="text-sm font-medium text-tx">{r.chief_complaint}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-tx-3">
                <Badge>{t(`record.type_${r.type}`)}</Badge>
                {r.location_name}
              </p>
            </>
          )
          return (
            <div key={r.id} className="relative">
              <span className="absolute -left-[26px] top-1 h-3.5 w-3.5 -translate-x-1/2 rounded-full border-2 border-accent bg-surface" />
              {onOpen ? (
                <button
                  onClick={() => onOpen(r.id)}
                  className="block w-full rounded-lg px-2 py-1 text-left transition-colors hover:bg-surface-2"
                >
                  {body}
                </button>
              ) : (
                <div className="px-2 py-1">{body}</div>
              )}
            </div>
          )
        })}
      </div>
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

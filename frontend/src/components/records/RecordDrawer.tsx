import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FilePen, ShieldAlert, ShieldCheck } from 'lucide-react'
import { recordsApi } from '@/api/records'
import { AmendRecordModal } from '@/components/records/AmendRecordModal'
import { RecordCertificates, RecordPrintActions } from '@/components/records/RecordDocuments'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/cn'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { sectionTitle, templateName } from '@/lib/notes'
import { useFill } from '@/lib/printing'
import { useAuthStore } from '@/stores/auth'
import type { RecordVersion } from '@/types'

export function RecordDrawer({
  recordId,
  onClose,
}: {
  recordId: string | null
  onClose: () => void
}) {
  const t = useT()
  const canAmend = useAuthStore((s) => s.can('records.amend'))
  const canReadClinical = useAuthStore((s) => s.can('records.read_clinical'))
  const userId = useAuthStore((s) => s.session?.user_id)
  const [amendOpen, setAmendOpen] = useState(false)
  // The version on screen: starts at the one that was opened and follows the version links.
  const [viewId, setViewId] = useState(recordId)
  useEffect(() => setViewId(recordId), [recordId])
  const { data: record, isLoading } = useQuery({
    queryKey: ['record', viewId],
    queryFn: () => recordsApi.get(viewId!),
    enabled: !!viewId && canReadClinical,
  })
  const hasVersions = !!record && (record.status === 'amended' || !record.is_current)
  const versions = useQuery({
    queryKey: ['record', viewId, 'versions'],
    queryFn: () => recordsApi.versions(viewId!),
    enabled: hasVersions && canReadClinical,
  })
  // Only the author amends, and only the current version.
  const canAmendThis =
    canAmend &&
    !!record &&
    record.status !== 'draft' &&
    record.is_current &&
    userId === record.author_id
  const currentId = versions.data?.find((v) => v.is_current)?.id ?? record?.superseded_by_id

  return (
    <Drawer open={!!recordId} onClose={onClose}>
      {isLoading || !record ? (
        <div className="flex h-full items-center justify-center">
          <Spinner />
        </div>
      ) : (
        <div className="p-8">
          {/* Strip */}
          <div className="flex items-start justify-between border-b border-line pb-5">
            <div>
              <p className="font-mono text-[13px] text-tx-3">{record.code}</p>
              <h2 className="mt-1 font-serif text-2xl text-tx">{record.chief_complaint}</h2>
              <p className="mt-1 text-[13px] text-tx-3">
                {record.location_name} · {fmtDateTimeTz(record.encounter_at)}
              </p>
              <p className="mt-2 inline-flex items-center gap-1.5 text-[13px] text-tx-3">
                <ShieldCheck className="h-3.5 w-3.5 text-accent" />
                {record.insurer_name
                  ? `${t('record.insurer')} · ${record.insurer_name}`
                  : t('record.private')}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {canAmendThis && (
                <Button size="sm" variant="outline" onClick={() => setAmendOpen(true)}>
                  <FilePen className="h-3.5 w-3.5" />
                  {t('record.amend')}
                </Button>
              )}
              <Badge tone={record.status === 'amended' ? 'info' : 'ok'}>
                {t(`records.${record.status === 'amended' ? 'amended' : 'signed'}`)}
              </Badge>
            </div>
          </div>

          {record.integrity && record.integrity !== 'ok' && (
            <div
              role="alert"
              className={cn(
                'mt-4 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm text-tx',
                record.integrity === 'tampered' ? 'border-danger' : 'border-warn',
              )}
            >
              <ShieldAlert
                className={cn(
                  'mt-0.5 h-4 w-4 shrink-0',
                  record.integrity === 'tampered' ? 'text-danger' : 'text-warn',
                )}
              />
              <span>
                {t(
                  record.integrity === 'tampered'
                    ? 'record.integrity_tampered'
                    : 'record.integrity_unverifiable',
                )}
              </span>
            </div>
          )}

          {!record.is_current && (
            <div
              role="status"
              className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-warn px-3 py-2 text-sm text-tx"
            >
              <span>{t('record.superseded_banner')}</span>
              {currentId && (
                <Button size="sm" variant="outline" onClick={() => setViewId(currentId)}>
                  {t('record.view_current')}
                </Button>
              )}
            </div>
          )}

          {record.is_current && (
            <div className="mt-4">
              <RecordPrintActions record={record} />
            </div>
          )}

          {/* Vitals */}
          {Object.values(record.vitals).some((v) => v !== null) && (
            <section className="mt-5">
              <p className="eyebrow mb-2">{t('consult.vitals')}</p>
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                {record.vitals.blood_pressure && <Vital label={t('vital.blood_pressure')} value={record.vitals.blood_pressure} />}
                {record.vitals.heart_rate != null && <Vital label={t('vital.heart_rate')} value={String(record.vitals.heart_rate)} />}
                {record.vitals.spo2 != null && <Vital label={t('vital.spo2')} value={`${record.vitals.spo2}%`} />}
                {record.vitals.temperature && <Vital label={t('vital.temperature')} value={`${record.vitals.temperature}°`} />}
                {record.vitals.weight && <Vital label={t('vital.weight')} value={`${record.vitals.weight}kg`} />}
                {record.vitals.glucose != null && <Vital label={t('vital.glucose')} value={String(record.vitals.glucose)} />}
              </div>
            </section>
          )}

          {/* Clinical note, in the template it was signed with */}
          <section className="mt-6 space-y-4">
            <p className="text-xs text-tx-3">
              {t('note.title')} · {templateName(t, record.note.template, record.note.name)}
            </p>
            {record.note.sections
              .filter((s) => s.text.trim())
              .map((s) => (
                <div key={s.key}>
                  <p className="eyebrow mb-1">{sectionTitle(t, record.note.template, s)}</p>
                  <p className="whitespace-pre-wrap text-sm text-tx">{s.text}</p>
                </div>
              ))}
          </section>

          {/* Diagnoses */}
          {record.diagnoses.length > 0 && (
            <section className="mt-6">
              <p className="eyebrow mb-2">{t('consult.diagnoses')}</p>
              <div className="space-y-1.5">
                {record.diagnoses.map((d) => (
                  <div key={d.code} className="flex items-center gap-2">
                    <span className="font-mono text-[13px] font-medium text-accent">{d.code}</span>
                    <span className="text-sm text-tx">{d.label}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Prescriptions */}
          {record.prescriptions.length > 0 && (
            <section className="mt-6">
              <p className="eyebrow mb-2">{t('consult.prescriptions')}</p>
              <div className="space-y-1.5">
                {record.prescriptions.map((p, i) => (
                  <div key={i} className="rounded-lg border border-line px-3 py-2">
                    <p className="text-sm font-medium text-tx">{p.drug}</p>
                    <p className="text-xs text-tx-3">
                      {p.dose} · {p.schedule}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Exam orders */}
          {record.exams.length > 0 && (
            <section className="mt-6">
              <p className="eyebrow mb-2">{t('record.exams')}</p>
              <div className="space-y-1.5">
                {record.exams.map((e, i) => (
                  <div key={i} className="rounded-lg border border-line px-3 py-2">
                    <p className="text-sm font-medium text-tx">{e.name}</p>
                    <p className="text-xs text-tx-3">
                      {t(`exam.kind.${e.kind}`)}
                      {e.notes ? ` · ${e.notes}` : ''}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {record.is_current && <RecordCertificates recordId={record.id} />}

          {hasVersions && (
            <section className="mt-6" aria-labelledby="record-versions-title">
              <h3 id="record-versions-title" className="eyebrow mb-2">
                {t('record.versions')}
              </h3>
              {versions.isError ? (
                <p role="alert" className="text-sm text-danger">
                  {t('record.versions_error')}
                </p>
              ) : versions.isLoading ? (
                <Spinner />
              ) : (
                <ol className="space-y-1.5">
                  {versions.data?.map((v) => (
                    <li key={v.id}>
                      <VersionRow
                        version={v}
                        isShown={v.id === record.id}
                        onOpen={() => setViewId(v.id)}
                      />
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}

          {/* Signer */}
          <div className="mt-8 flex items-center gap-2 border-t border-line pt-5 text-[13px] text-tx-3">
            <Avatar name={record.signed_by_name ?? '—'} size="sm" />
            <span>
              {t('record.signed_by')}{' '}
              <span className="font-medium text-tx">{record.signed_by_name ?? '—'}</span>
              {' · '}
              {fmtDateTimeTz(record.signed_at)}
            </span>
          </div>
        </div>
      )}
      <AmendRecordModal
        record={amendOpen && record ? record : null}
        onClose={() => setAmendOpen(false)}
        onAmended={(amendment) => setViewId(amendment.id)}
        onOpenRecord={setViewId}
      />
    </Drawer>
  )
}

function VersionRow({
  version,
  isShown,
  onOpen,
}: {
  version: RecordVersion
  isShown: boolean
  onOpen: () => void
}) {
  const t = useT()
  const f = useFill()
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-current={isShown ? 'true' : undefined}
      className={cn(
        'block w-full rounded-lg border px-3 py-2 text-left transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
        isShown ? 'border-accent bg-surface' : 'border-line hover:bg-surface',
      )}
    >
      <span className="flex items-center gap-2">
        <span className="text-sm font-medium text-tx">
          {f('record.version_n', { n: version.version })}
        </span>
        {version.is_current && <Badge tone="ok">{t('record.current')}</Badge>}
        {version.integrity !== 'ok' && (
          <Badge tone={version.integrity === 'tampered' ? 'danger' : 'warn'}>
            {t(
              version.integrity === 'tampered'
                ? 'record.integrity_badge_tampered'
                : 'record.integrity_badge_unverifiable',
            )}
          </Badge>
        )}
      </span>
      <span className="mt-0.5 block text-xs text-tx-3">
        {version.signed_by_name ?? '—'} · {fmtDateTimeTz(version.signed_at)}
      </span>
      {version.amendment_reason && (
        <span className="mt-1 block whitespace-pre-wrap text-sm text-tx">
          <span className="text-tx-3">{t('record.reason_label')}: </span>
          {version.amendment_reason}
        </span>
      )}
    </button>
  )
}

function Vital({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-2.5 text-center">
      <p className="eyebrow">{label}</p>
      <p className="mt-0.5 font-serif text-lg text-tx">{value}</p>
    </div>
  )
}

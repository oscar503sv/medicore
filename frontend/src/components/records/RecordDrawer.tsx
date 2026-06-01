import { useQuery } from '@tanstack/react-query'
import { recordsApi } from '@/api/records'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Drawer } from '@/components/ui/Drawer'
import { Spinner } from '@/components/ui/Spinner'
import { fmtDateTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Soap } from '@/types'

const SOAP_ORDER: { key: keyof Soap; labelKey: string }[] = [
  { key: 'subjective', labelKey: 'consult.subjective' },
  { key: 'objective', labelKey: 'consult.objective' },
  { key: 'assessment', labelKey: 'consult.assessment' },
  { key: 'plan', labelKey: 'consult.plan' },
]

export function RecordDrawer({
  recordId,
  onClose,
}: {
  recordId: string | null
  onClose: () => void
}) {
  const t = useT()
  const { data: record, isLoading } = useQuery({
    queryKey: ['record', recordId],
    queryFn: () => recordsApi.get(recordId!),
    enabled: !!recordId,
  })

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
                {record.location_name} · {fmtDateTime(record.encounter_at)}
              </p>
            </div>
            <Badge tone={record.status === 'amended' ? 'info' : 'ok'}>
              {t(`records.${record.status === 'amended' ? 'amended' : 'signed'}`)}
            </Badge>
          </div>

          {/* Vitals */}
          {Object.values(record.vitals).some((v) => v !== null) && (
            <section className="mt-5">
              <p className="eyebrow mb-2">{t('consult.vitals')}</p>
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                {record.vitals.blood_pressure && <Vital label="TA" value={record.vitals.blood_pressure} />}
                {record.vitals.heart_rate != null && <Vital label="FC" value={String(record.vitals.heart_rate)} />}
                {record.vitals.spo2 != null && <Vital label="SpO₂" value={`${record.vitals.spo2}%`} />}
                {record.vitals.temperature && <Vital label="Temp" value={`${record.vitals.temperature}°`} />}
                {record.vitals.weight && <Vital label="Peso" value={`${record.vitals.weight}kg`} />}
                {record.vitals.glucose != null && <Vital label="Gluc" value={String(record.vitals.glucose)} />}
              </div>
            </section>
          )}

          {/* SOAP */}
          <section className="mt-6 space-y-4">
            {SOAP_ORDER.map(
              (f) =>
                record.soap[f.key] && (
                  <div key={f.key}>
                    <p className="eyebrow mb-1">{t(f.labelKey)}</p>
                    <p className="whitespace-pre-wrap text-sm text-tx">{record.soap[f.key]}</p>
                  </div>
                ),
            )}
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
                {record.prescriptions.map((rx, i) => {
                  const p = rx as { drug: string; dose: string; schedule: string }
                  return (
                    <div key={i} className="rounded-lg border border-line px-3 py-2">
                      <p className="text-sm font-medium text-tx">{p.drug}</p>
                      <p className="text-xs text-tx-3">
                        {p.dose} · {p.schedule}
                      </p>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {/* Author */}
          <div className="mt-8 flex items-center gap-2 border-t border-line pt-5 text-[13px] text-tx-3">
            <Avatar name="Médico" size="sm" />
            Firmado el {fmtDateTime(record.signed_at)}
          </div>
        </div>
      )}
    </Drawer>
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

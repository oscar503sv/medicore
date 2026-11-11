import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileBadge, FileText, FlaskConical, Pill, Printer } from 'lucide-react'
import { authApi } from '@/api/auth'
import { certificatesApi } from '@/api/certificates'
import { errorMessage } from '@/api/client'
import { openPrint } from '@/api/printing'
import { ReasonModal } from '@/components/applications/ReasonModal'
import { IssueCertificateModal } from '@/components/records/IssueCertificateModal'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toast'
import { fmtDate, fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useFill } from '@/lib/printing'
import { useAuthStore } from '@/stores/auth'
import type { MedicalCertificate, MedicalRecord } from '@/types'

type RecordLike = Pick<MedicalRecord, 'id' | 'author_id' | 'prescriptions' | 'exams' | 'diagnoses'>

/** The documents a signed visit can print: prescription, exam order, record copy and medical
 * certificates (issued only by the doctor who signed it). */
export function RecordPrintActions({ record }: { record: RecordLike }) {
  const t = useT()
  const userId = useAuthStore((s) => s.session?.user_id)
  const canSign = useAuthStore((s) => s.can('records.sign'))
  const isAuthor = canSign && userId === record.author_id
  const [certFor, setCertFor] = useState<RecordLike | null>(null)
  const { data: profile } = useQuery({
    queryKey: ['my-profile'],
    queryFn: authApi.getMyProfile,
    enabled: isAuthor,
  })

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {record.prescriptions.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => openPrint(`prescription/${record.id}`)}
          >
            <Pill className="h-3.5 w-3.5" />
            {t('pr.btn.prescription')}
          </Button>
        )}
        {record.exams.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => openPrint(`exams/${record.id}`)}>
            <FlaskConical className="h-3.5 w-3.5" />
            {t('pr.btn.exams')}
          </Button>
        )}
        {isAuthor && (
          <Button size="sm" variant="outline" onClick={() => setCertFor(record)}>
            <FileBadge className="h-3.5 w-3.5" />
            {t('pr.btn.certificate')}
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => openPrint(`record/${record.id}`)}>
          <FileText className="h-3.5 w-3.5" />
          {t('pr.btn.record')}
        </Button>
      </div>
      {isAuthor && profile && !profile.jvpm && (
        <p className="mt-2 text-xs text-warn">{t('user.jvpm_missing')}</p>
      )}
      <IssueCertificateModal record={certFor} onClose={() => setCertFor(null)} />
    </div>
  )
}

/** Certificates issued for a visit: reprint, or void (the issuing doctor only). */
export function RecordCertificates({ recordId }: { recordId: string }) {
  const t = useT()
  const f = useFill()
  const qc = useQueryClient()
  const userId = useAuthStore((s) => s.session?.user_id)
  const [voiding, setVoiding] = useState<MedicalCertificate | null>(null)
  const { data = [] } = useQuery({
    queryKey: ['certificates', 'record', recordId],
    queryFn: () => certificatesApi.forRecord(recordId),
  })
  const voidCert = useMutation({
    mutationFn: (reason: string) => certificatesApi.void(voiding!.id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['certificates'] })
      toast(t('cert.voided_ok'))
      setVoiding(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  if (data.length === 0) return null

  return (
    <section className="mt-6">
      <p className="eyebrow mb-2">{t('cert.title')}</p>
      <div className="space-y-1.5">
        {data.map((c) => (
          <div
            key={c.id}
            className="flex items-center gap-3 rounded-lg border border-line px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-tx">
                {t(`cert.kind.${c.kind}`)}{' '}
                <span className="font-mono text-xs text-tx-3">{c.code}</span>
              </p>
              <p className="text-xs text-tx-3">
                {c.kind === 'rest'
                  ? f('cert.rest_summary', {
                      n: c.rest_days ?? 0,
                      from: fmtDate(c.rest_from, 'd MMM'),
                      to: fmtDate(c.rest_until, 'd MMM'),
                    })
                  : fmtDateTz(c.issued_at)}
                {c.voided_at && ` · ${c.void_reason}`}
              </p>
            </div>
            {c.voided_at ? (
              <Badge tone="neutral">{t('cert.voided')}</Badge>
            ) : (
              <>
                <Button size="sm" variant="ghost" onClick={() => openPrint(`certificate/${c.id}`)}>
                  <Printer className="h-3.5 w-3.5" />
                  {t('cert.reprint')}
                </Button>
                {c.doctor_id === userId && (
                  <Button size="sm" variant="ghost" onClick={() => setVoiding(c)}>
                    {t('cert.void')}
                  </Button>
                )}
              </>
            )}
          </div>
        ))}
      </div>
      <ReasonModal
        open={!!voiding}
        title={t('cert.void_title')}
        description={voiding ? `${t(`cert.kind.${voiding.kind}`)} · ${voiding.code}` : ''}
        confirmLabel={t('cert.void')}
        loading={voidCert.isPending}
        onConfirm={(reason) => voidCert.mutate(reason)}
        onClose={() => setVoiding(null)}
      />
    </section>
  )
}

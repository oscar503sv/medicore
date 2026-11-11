import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { certificatesApi } from '@/api/certificates'
import { errorMessage } from '@/api/client'
import { openPrint } from '@/api/printing'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Segmented } from '@/components/ui/Segmented'
import { toast } from '@/components/ui/Toast'
import { clinicToday } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { CertificateKind, MedicalRecord } from '@/types'

/** Issue a medical certificate for a signed visit, then open it to print. */
export function IssueCertificateModal({
  record,
  onClose,
}: {
  record: Pick<MedicalRecord, 'id' | 'diagnoses'> | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [kind, setKind] = useState<CertificateKind>('rest')
  const [restFrom, setRestFrom] = useState(clinicToday())
  const [restDays, setRestDays] = useState('3')
  const [withDiagnosis, setWithDiagnosis] = useState(false)
  const [addressee, setAddressee] = useState('')
  const [remarks, setRemarks] = useState('')

  useEffect(() => {
    if (record) {
      setKind('rest')
      setRestFrom(clinicToday())
      setRestDays('3')
      setWithDiagnosis(false)
      setAddressee('')
      setRemarks('')
    }
  }, [record])

  const issue = useMutation({
    mutationFn: () =>
      certificatesApi.issue(record!.id, {
        kind,
        rest_from: kind === 'rest' ? restFrom : null,
        rest_days: kind === 'rest' ? Number(restDays) : null,
        include_diagnosis: withDiagnosis,
        addressee: addressee.trim() || null,
        remarks: remarks.trim() || null,
      }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['certificates'] })
      toast(t('cert.issued_ok'))
      openPrint(`certificate/${c.id}`)
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const hasDiagnoses = (record?.diagnoses.length ?? 0) > 0
  const valid = kind === 'attendance' || (!!restFrom && Number(restDays) >= 1)

  return (
    <Modal open={!!record} onClose={onClose} title={t('cert.issue')} width="max-w-md">
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          issue.mutate()
        }}
      >
        <div>
          <p className="mb-1.5 text-[13px] font-medium text-tx-2">{t('cert.kind')}</p>
          <Segmented
            value={kind}
            onChange={setKind}
            options={(['rest', 'attendance'] as CertificateKind[]).map((k) => ({
              value: k,
              label: t(`cert.kind.${k}`),
            }))}
          />
        </div>
        {kind === 'rest' && (
          <div className="grid grid-cols-2 gap-3">
            <Input
              type="date"
              label={t('cert.rest_from')}
              value={restFrom}
              onChange={(e) => setRestFrom(e.target.value)}
              required
            />
            <Input
              type="number"
              min={1}
              max={90}
              label={t('cert.rest_days')}
              value={restDays}
              onChange={(e) => setRestDays(e.target.value)}
              required
            />
          </div>
        )}
        <label className="flex items-start gap-2.5">
          <Checkbox
            checked={withDiagnosis}
            disabled={!hasDiagnoses}
            onChange={(e) => setWithDiagnosis(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            <span className="block text-sm text-tx">{t('cert.include_diagnosis')}</span>
            <span className="block text-xs text-tx-3">
              {hasDiagnoses ? t('cert.include_diagnosis_hint') : t('cert.no_diagnosis')}
            </span>
          </span>
        </label>
        <Input
          label={t('cert.addressee')}
          placeholder={t('cert.addressee_ph')}
          value={addressee}
          maxLength={200}
          onChange={(e) => setAddressee(e.target.value)}
        />
        <Textarea
          label={t('cert.remarks')}
          rows={3}
          maxLength={1000}
          value={remarks}
          onChange={(e) => setRemarks(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={issue.isPending} disabled={!valid}>
            {t('cert.issue')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

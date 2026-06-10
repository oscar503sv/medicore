import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { recordsApi } from '@/api/records'
import { Button } from '@/components/ui/Button'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { MedicalRecord, Soap } from '@/types'

const SOAP_ORDER: { key: keyof Soap; labelKey: string }[] = [
  { key: 'subjective', labelKey: 'consult.subjective' },
  { key: 'objective', labelKey: 'consult.objective' },
  { key: 'assessment', labelKey: 'consult.assessment' },
  { key: 'plan', labelKey: 'consult.plan' },
]

export function AmendRecordModal({
  record,
  onClose,
}: {
  record: MedicalRecord | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [chiefComplaint, setChiefComplaint] = useState('')
  const [soap, setSoap] = useState<Soap>({ subjective: '', objective: '', assessment: '', plan: '' })

  // Prefill from the record being amended each time the modal opens.
  useEffect(() => {
    if (record) {
      setChiefComplaint(record.chief_complaint)
      setSoap({ ...record.soap })
    }
  }, [record])

  const amend = useMutation({
    mutationFn: () =>
      recordsApi.amend(record!.id, { chief_complaint: chiefComplaint, soap: { ...soap } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] })
      qc.invalidateQueries({ queryKey: ['record', record!.id] })
      toast(t('record.amend_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={!!record} onClose={onClose} title={t('record.amend_title')} width="max-w-2xl">
      <div className="space-y-4 p-5">
        <p className="text-sm text-tx-3">{t('record.amend_note')}</p>
        <Input
          label={t('record.chief_complaint')}
          value={chiefComplaint}
          onChange={(e) => setChiefComplaint(e.target.value)}
        />
        {SOAP_ORDER.map((f) => (
          <Textarea
            key={f.key}
            label={t(f.labelKey)}
            rows={3}
            value={soap[f.key]}
            onChange={(e) => setSoap((s) => ({ ...s, [f.key]: e.target.value }))}
          />
        ))}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button
            loading={amend.isPending}
            disabled={!chiefComplaint.trim()}
            onClick={() => amend.mutate()}
          >
            {t('record.amend')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

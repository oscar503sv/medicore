import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { recordsApi } from '@/api/records'
import { Button } from '@/components/ui/Button'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { sectionTitle } from '@/lib/notes'
import type { MedicalRecord } from '@/types'

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
  // Section key → text, in the template the record was signed with.
  const [note, setNote] = useState<Record<string, string>>({})

  // Prefill from the record being amended each time the modal opens.
  useEffect(() => {
    if (record) {
      setChiefComplaint(record.chief_complaint)
      setNote(Object.fromEntries(record.note.sections.map((s) => [s.key, s.text])))
    }
  }, [record])

  const amend = useMutation({
    mutationFn: () =>
      recordsApi.amend(record!.id, { chief_complaint: chiefComplaint, note: { ...note } }),
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
        {record?.note.sections.map((s) => (
          <Textarea
            key={s.key}
            label={sectionTitle(t, record.note.template, s)}
            rows={s.role === 'free' ? 8 : 3}
            value={note[s.key] ?? ''}
            onChange={(e) => setNote((n) => ({ ...n, [s.key]: e.target.value }))}
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

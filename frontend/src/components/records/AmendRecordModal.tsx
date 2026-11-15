import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorCode, errorMessage, errorParams } from '@/api/client'
import { recordsApi } from '@/api/records'
import { Button } from '@/components/ui/Button'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { sectionTitle } from '@/lib/notes'
import { useFill } from '@/lib/printing'
import type { MedicalRecord } from '@/types'

const REASON_MIN = 10
const REASON_MAX = 1000
// Query keys that show a record, its lists or what hangs from it (vitals, certificates).
const INVALIDATED = ['record', 'records', 'patient', 'vitals', 'certificates']

export function AmendRecordModal({
  record,
  onClose,
  onAmended,
  onOpenRecord,
}: {
  record: MedicalRecord | null
  onClose: () => void
  /** Called with the new version, so the caller can show it. */
  onAmended?: (amendment: MedicalRecord) => void
  /** Called with the id of the current version when this one was replaced meanwhile. */
  onOpenRecord?: (id: string) => void
}) {
  const t = useT()
  const f = useFill()
  const qc = useQueryClient()
  const [chiefComplaint, setChiefComplaint] = useState('')
  // Section key → text, in the template the record was signed with.
  const [note, setNote] = useState<Record<string, string>>({})
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const [currentId, setCurrentId] = useState<string | null>(null)

  // Prefill from the record being amended each time the modal opens.
  useEffect(() => {
    if (record) {
      setChiefComplaint(record.chief_complaint)
      setNote(Object.fromEntries(record.note.sections.map((s) => [s.key, s.text])))
      setReason('')
      setReasonError(null)
      setCurrentId(null)
    }
  }, [record])

  const invalidate = () => INVALIDATED.forEach((key) => qc.invalidateQueries({ queryKey: [key] }))

  const amend = useMutation({
    mutationFn: () =>
      recordsApi.amend(record!.id, {
        reason: reason.trim(),
        chief_complaint: chiefComplaint,
        note: { ...note },
      }),
    onSuccess: (amendment) => {
      invalidate()
      toast(t('record.amend_ok'))
      onAmended?.(amendment)
      onClose()
    },
    onError: (err) => {
      const code = errorCode(err)
      if (code === 'record.amend_reason_invalid') {
        setReasonError(errorMessage(err))
      } else if (code === 'record.superseded') {
        const id = errorParams(err).current_id
        setCurrentId(typeof id === 'string' ? id : null)
        invalidate()
      } else {
        toast(errorMessage(err), 'danger')
      }
    },
  })

  const changed =
    !!record &&
    (chiefComplaint.trim() !== record.chief_complaint.trim() ||
      record.note.sections.some((s) => (note[s.key] ?? '').trim() !== s.text.trim()))
  const reasonLength = reason.trim().length
  const canSubmit =
    changed && !!chiefComplaint.trim() && reasonLength >= REASON_MIN && reasonLength <= REASON_MAX

  return (
    <Modal open={!!record} onClose={onClose} title={t('record.amend_title')} width="max-w-2xl">
      <div className="space-y-4 p-5">
        <p className="text-sm text-tx-3">{t('record.amend_note')}</p>
        {currentId && (
          <div role="alert" className="rounded-lg border border-warn p-3 text-sm text-tx">
            <p>{t('record.amend_superseded')}</p>
            {onOpenRecord && (
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                onClick={() => {
                  onOpenRecord(currentId)
                  onClose()
                }}
              >
                {t('record.view_current')}
              </Button>
            )}
          </div>
        )}
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
        <Textarea
          label={t('record.amend_reason')}
          rows={3}
          required
          maxLength={REASON_MAX}
          value={reason}
          hint={t('record.amend_reason_hint')}
          aside={f('record.amend_reason_count', { n: reason.length })}
          error={reasonError ?? undefined}
          onChange={(e) => {
            setReason(e.target.value)
            setReasonError(null)
          }}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button loading={amend.isPending} disabled={!canSubmit} onClick={() => amend.mutate()}>
            {t('record.amend')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

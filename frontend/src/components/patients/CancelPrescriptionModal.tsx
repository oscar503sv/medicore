import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorCode, errorMessage } from '@/api/client'
import { prescriptionsApi } from '@/api/prescriptions'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { useFill } from '@/lib/printing'
import type { Prescription } from '@/types'

const REASON_MIN = 10
const REASON_MAX = 500

/** Stopping a treatment early is a clinical decision: it needs a reason that stays on record. */
export function CancelPrescriptionModal({
  prescription,
  onClose,
}: {
  prescription: Prescription | null
  onClose: () => void
}) {
  const t = useT()
  const f = useFill()
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)

  useEffect(() => {
    setReason('')
    setReasonError(null)
  }, [prescription])

  const cancel = useMutation({
    mutationFn: () => prescriptionsApi.cancel(prescription!.id, reason.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prescriptions', prescription!.patient_id] })
      // The summary's active-prescriptions counter comes from the patient detail.
      qc.invalidateQueries({ queryKey: ['patient', prescription!.patient_id] })
      toast(t('rx.cancelled_ok'))
      onClose()
    },
    onError: (err) => {
      if (errorCode(err) === 'prescription.cancel_reason_invalid') {
        setReasonError(errorMessage(err))
      } else {
        toast(errorMessage(err), 'danger')
        if (prescription)
          qc.invalidateQueries({ queryKey: ['prescriptions', prescription.patient_id] })
      }
    },
  })

  const reasonLength = reason.trim().length
  const canSubmit = reasonLength >= REASON_MIN && reasonLength <= REASON_MAX

  return (
    <Modal
      open={prescription !== null}
      onClose={onClose}
      title={t('rx.cancel_title')}
      width="max-w-md"
    >
      {prescription && (
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            if (canSubmit) cancel.mutate()
          }}
        >
          <p className="text-sm text-tx-2">{t('rx.cancel_desc')}</p>
          <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
            <p className="font-medium text-tx">{prescription.drug}</p>
            <p className="text-xs text-tx-3">
              {prescription.dose} · {prescription.schedule}
            </p>
          </div>
          <Textarea
            label={t('rx.cancel_reason')}
            rows={3}
            required
            autoFocus
            maxLength={REASON_MAX}
            value={reason}
            hint={t('rx.cancel_reason_hint')}
            aside={f('rx.cancel_reason_count', { n: reason.length })}
            error={reasonError ?? undefined}
            onChange={(e) => {
              setReason(e.target.value)
              setReasonError(null)
            }}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.back')}
            </Button>
            <Button type="submit" variant="danger" loading={cancel.isPending} disabled={!canSubmit}>
              {t('rx.cancel_confirm')}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

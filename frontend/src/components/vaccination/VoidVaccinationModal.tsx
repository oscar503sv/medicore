import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { vaccinationsApi, type VaccinationRecord } from '@/api/vaccinations'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { vaccineName } from '@/lib/vaccination'

/** Void a wrong entry: it stays in the history, struck through, with who/when/why. */
export function VoidVaccinationModal({
  record,
  onClose,
}: {
  record: VaccinationRecord | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  useEffect(() => setReason(''), [record])

  const voidIt = useMutation({
    mutationFn: () => vaccinationsApi.void(record!.id, reason.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vaccination-card', record!.patient_id] })
      qc.invalidateQueries({ queryKey: ['vaccination-worklist'] })
      toast(t('vax.void_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={record !== null} onClose={onClose} title={t('vax.void_title')} width="max-w-md">
      {record && (
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            voidIt.mutate()
          }}
        >
          <p className="text-sm text-tx-2">{t('vax.void_desc')}</p>
          <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
            <p className="font-medium text-tx">{vaccineName(t, record.vaccine_code)}</p>
            <p className="font-mono text-xs text-tx-3">
              {fmtDate(record.occurred_on)}
              {record.lot && ` · ${record.lot}`}
            </p>
          </div>
          <Input
            label={t('vax.void_reason')}
            value={reason}
            placeholder={t('vax.void_reason_ph')}
            onChange={(e) => setReason(e.target.value)}
            autoFocus
            required
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.back')}
            </Button>
            <Button
              type="submit"
              variant="danger"
              loading={voidIt.isPending}
              disabled={!reason.trim()}
            >
              {t('vax.void')}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

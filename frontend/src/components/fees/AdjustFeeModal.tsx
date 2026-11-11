import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { FEE_PATTERN, fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'

/** Change what a visit is charged: an amount and, when it differs from the listed fee,
 * the reason. The caller runs the request. */
export function AdjustFeeModal({
  open,
  subtitle,
  listed,
  charged,
  note,
  loading,
  onClose,
  onSave,
}: {
  open: boolean
  subtitle: string
  listed: string | null
  charged: string | null
  note: string | null
  loading: boolean
  onClose: () => void
  onSave: (amount: string, note: string | null) => void
}) {
  const t = useT()
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')

  useEffect(() => {
    if (open) {
      setAmount(charged ?? listed ?? '')
      setReason(note ?? '')
    }
  }, [open, charged, listed, note])

  const valid = FEE_PATTERN.test(amount.trim())
  const differs = listed !== null && valid && Number(amount) !== Number(listed)
  const canSave = valid && (!differs || reason.trim().length > 0)

  return (
    <Modal open={open} onClose={onClose} title={t('fee.adjust_title')}>
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          if (canSave) onSave(amount.trim(), reason.trim() || null)
        }}
      >
        <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
          <p className="font-medium text-tx">{subtitle}</p>
          <p className="text-tx-3">
            {listed === null ? t('fee.none') : t('fee.listed').replace('{price}', fmtFee(listed)!)}
          </p>
        </div>
        <Input
          label={t('fee.amount')}
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="w-40 font-mono"
          autoFocus
        />
        <div>
          <Input
            label={t('fee.note')}
            placeholder={t('fee.note_ph')}
            maxLength={200}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="mt-1 text-xs text-tx-3">{t('fee.note_hint')}</p>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('fee.cancel')}
          </Button>
          <Button type="submit" disabled={!canSave} loading={loading}>
            {t('fee.save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

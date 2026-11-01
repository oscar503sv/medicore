import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { useT } from '@/lib/i18n'

/** Ask for a reason before a destructive action (cancel an order, void a record). */
export function ReasonModal({
  open,
  title,
  description,
  confirmLabel,
  loading,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  loading?: boolean
  onConfirm: (reason: string) => void
  onClose: () => void
}) {
  const t = useT()
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) setReason('')
  }, [open])
  return (
    <Modal open={open} onClose={onClose} title={title} width="max-w-md">
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          onConfirm(reason.trim())
        }}
      >
        <p className="text-sm text-tx-2">{description}</p>
        <Input
          label={t('apl.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          autoFocus
          required
        />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.back')}
          </Button>
          <Button type="submit" variant="danger" loading={loading} disabled={!reason.trim()}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

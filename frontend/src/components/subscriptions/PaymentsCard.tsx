import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformPlansApi } from '@/api/platform'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { fmtUsd, renewedUntil } from '@/lib/subscriptions'
import {
  PAYMENT_METHODS,
  type PaymentMethod,
  type Subscription,
  type SubscriptionPayment,
} from '@/types'

const MONTH_CHOICES = [1, 3, 6, 12]

/** Platform console: a clinic's payment history, and recording a payment (which renews). */
export function PaymentsCard({
  tenantId,
  onRecorded,
}: {
  tenantId: string
  onRecorded: () => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const { data: payments } = useQuery({
    queryKey: ['platform-payments', tenantId],
    queryFn: () => platformPlansApi.payments(tenantId),
  })
  const { data: sub } = useQuery({
    queryKey: ['platform-subscription', tenantId],
    queryFn: () => platformPlansApi.subscription(tenantId),
  })

  return (
    <Card>
      <CardHeader
        title={t('sub.payments_title')}
        action={
          <Button size="sm" onClick={() => setOpen(true)} disabled={!sub}>
            <Banknote className="h-3.5 w-3.5" />
            {t('sub.record_payment')}
          </Button>
        }
      />
      <PaymentsTable payments={payments ?? []} />
      {open && sub && (
        <RecordPaymentModal
          tenantId={tenantId}
          sub={sub}
          onClose={() => setOpen(false)}
          onRecorded={onRecorded}
        />
      )}
    </Card>
  )
}

export function PaymentsTable({ payments }: { payments: SubscriptionPayment[] }) {
  const t = useT()
  if (payments.length === 0) {
    return <p className="px-5 py-6 text-center text-[13px] text-tx-3">{t('sub.no_payments')}</p>
  }
  return (
    <Table>
      <thead>
        <Tr>
          <Th>{t('sub.col_paid_on')}</Th>
          <Th>{t('sub.col_amount')}</Th>
          <Th>{t('sub.col_covers')}</Th>
          <Th>{t('sub.col_until')}</Th>
          <Th>{t('sub.f_method')}</Th>
          <Th>{t('sub.f_reference')}</Th>
        </Tr>
      </thead>
      <tbody>
        {payments.map((p) => (
          <Tr key={p.id}>
            <Td>{fmtDate(p.paid_on)}</Td>
            <Td className="font-mono">{fmtUsd(p.amount)}</Td>
            <Td>{monthsLabel(t, p.months)}</Td>
            <Td>{fmtDate(p.period_end)}</Td>
            <Td>{t(`sub.method.${p.method}`)}</Td>
            <Td>
              <p className="text-sm text-tx">{p.reference ?? '—'}</p>
              {p.notes && <p className="text-xs text-tx-3">{p.notes}</p>}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

function monthsLabel(t: (k: string) => string, n: number): string {
  return n === 1 ? t('sub.month_1') : t('sub.months_n').replace('{n}', String(n))
}

function RecordPaymentModal({
  tenantId,
  sub,
  onClose,
  onRecorded,
}: {
  tenantId: string
  sub: Subscription
  onClose: () => void
  onRecorded: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const suggested = (m: number) =>
    sub.monthly_price ? (Number(sub.monthly_price) * m).toFixed(2) : ''
  const [months, setMonths] = useState(1)
  const [amount, setAmount] = useState(suggested(1))
  const [paidOn, setPaidOn] = useState(sub.today)
  const [method, setMethod] = useState<PaymentMethod>('bank_transfer')
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')

  const save = useMutation({
    mutationFn: () =>
      platformPlansApi.recordPayment(tenantId, {
        amount,
        paid_on: paidOn,
        months,
        method,
        reference: reference || null,
        notes: notes || null,
      }),
    onSuccess: (res) => {
      qc.setQueryData(['platform-subscription', tenantId], res.subscription)
      qc.invalidateQueries({ queryKey: ['platform-payments', tenantId] })
      toast(t('sub.payment_ok').replace('{date}', fmtDate(res.payment.period_end)))
      onRecorded()
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open onClose={onClose} title={t('sub.record_payment')} width="max-w-lg">
      <form
        autoComplete="off"
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <p className="text-[13px] text-tx-3">{t('sub.payment_hint')}</p>
        <div className="grid grid-cols-2 gap-4">
          <Select
            label={t('sub.f_months')}
            value={String(months)}
            onChange={(e) => {
              const m = Number(e.target.value)
              setMonths(m)
              setAmount(suggested(m))
            }}
          >
            {MONTH_CHOICES.map((m) => (
              <option key={m} value={String(m)}>
                {monthsLabel(t, m)}
              </option>
            ))}
          </Select>
          <Input
            label={t('sub.f_amount')}
            type="number"
            min={0}
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
          <Input
            label={t('sub.f_paid_on')}
            type="date"
            value={paidOn}
            onChange={(e) => setPaidOn(e.target.value)}
            required
          />
          <Select
            label={t('sub.f_method')}
            value={method}
            onChange={(e) => setMethod(e.target.value as PaymentMethod)}
          >
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>
                {t(`sub.method.${m}`)}
              </option>
            ))}
          </Select>
          <Input
            label={t('sub.f_reference')}
            value={reference}
            maxLength={100}
            onChange={(e) => setReference(e.target.value)}
          />
          <Input
            label={t('sub.f_notes')}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-tx">
          {t('sub.new_period_end').replace('{date}', fmtDate(renewedUntil(sub, months)))}
        </p>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!amount}>
            {t('sub.record_payment')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

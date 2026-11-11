import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { type DoctorFees, feesApi, PRICED_TYPES } from '@/api/fees'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { FEE_PATTERN, fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { AppointmentType } from '@/types'

type Draft = Partial<Record<AppointmentType, string>>

/** The price list: every doctor's fee per appointment type. Everyone who books sees it;
 * a row is editable for whoever may set that doctor's fees. */
export function FeesPage() {
  const t = useT()
  const qc = useQueryClient()
  const userId = useAuthStore((s) => s.session?.user_id)
  const canProcedures = useAuthStore((s) => s.can('procedures.catalog'))
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>({})

  const { data, isLoading } = useQuery({ queryKey: ['fees'], queryFn: feesApi.list })

  const save = useMutation({
    mutationFn: (doctorId: string) => {
      const prices: Draft = {}
      for (const kind of PRICED_TYPES) {
        const value = draft[kind]?.trim()
        if (value) prices[kind] = value
      }
      return feesApi.update(doctorId, prices)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fees'] })
      toast(t('fee.saved'))
      setEditing(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const startEdit = (row: DoctorFees) => {
    setDraft(Object.fromEntries(PRICED_TYPES.map((k) => [k, row.prices[k] ?? ''])))
    setEditing(row.doctor_id)
  }
  const draftValid = PRICED_TYPES.every((k) => {
    const v = draft[k]?.trim() ?? ''
    return v === '' || FEE_PATTERN.test(v)
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('fee.title')} />
      <p className="-mt-2 max-w-3xl text-[13px] text-tx-3">{t('fee.subtitle')}</p>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : !data || data.length === 0 ? (
          <EmptyState title={t('fee.empty')} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t('fee.col_doctor')}</Th>
                {PRICED_TYPES.map((k) => (
                  <Th key={k} className="text-right">
                    {t(`apptype.${k}`)}
                  </Th>
                ))}
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.map((row) => {
                const isEditing = editing === row.doctor_id
                return (
                  <Tr key={row.doctor_id}>
                    <Td>
                      <span className="font-medium text-tx">{row.doctor_name}</span>
                      {row.doctor_id === userId && (
                        <span className="ml-2 text-xs text-tx-3">({t('fee.you')})</span>
                      )}
                    </Td>
                    {PRICED_TYPES.map((k) => (
                      <Td key={k} className="text-right">
                        {isEditing ? (
                          <input
                            aria-label={t(`apptype.${k}`)}
                            inputMode="decimal"
                            placeholder="—"
                            value={draft[k] ?? ''}
                            onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
                            className={cn(
                              'h-8 w-24 rounded-md border border-line bg-bg px-2 text-right font-mono text-sm text-tx',
                              'focus:border-accent focus:outline-none',
                              draft[k]?.trim() &&
                                !FEE_PATTERN.test(draft[k]!.trim()) &&
                                'border-danger',
                            )}
                          />
                        ) : row.prices[k] ? (
                          <span className="font-mono text-sm text-tx">{fmtFee(row.prices[k])}</span>
                        ) : (
                          <span className="text-xs text-tx-4">{t('fee.none')}</span>
                        )}
                      </Td>
                    ))}
                    <Td className="whitespace-nowrap text-right">
                      {isEditing ? (
                        <div className="flex justify-end gap-1.5">
                          <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
                            {t('fee.cancel')}
                          </Button>
                          <Button
                            size="sm"
                            disabled={!draftValid}
                            loading={save.isPending}
                            onClick={() => save.mutate(row.doctor_id)}
                          >
                            {t('fee.save')}
                          </Button>
                        </div>
                      ) : (
                        row.editable && (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={editing !== null}
                            onClick={() => startEdit(row)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                            {t('fee.edit')}
                          </Button>
                        )
                      )}
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        )}
        <div className="space-y-1 border-t border-line px-5 py-3 text-xs text-tx-3">
          {editing && <p>{t('fee.blank_hint')}</p>}
          <p>
            {t('fee.procedures_note')}{' '}
            {canProcedures && (
              <Link to="/procedures/catalog" className="text-accent hover:underline">
                {t('fee.catalog_link')}
              </Link>
            )}
          </p>
        </div>
      </Card>
    </div>
  )
}

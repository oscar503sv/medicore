import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { vaccinePricesApi, type VaccinePrice } from '@/api/fees'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { FEE_PATTERN, fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'
import { vaccineName } from '@/lib/vaccination'

/** The clinic's price per vaccine. Only private doses are charged: the ministry's (MINSAL)
 * are free by law, so they have no price here. */
export function VaccinePriceCard() {
  const t = useT()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['vaccine-prices'],
    queryFn: vaccinePricesApi.list,
  })

  const save = useMutation({
    mutationFn: ({ code, price }: { code: string; price: string | null }) =>
      vaccinePricesApi.set(code, price),
    onSuccess: (_, { price }) => {
      qc.invalidateQueries({ queryKey: ['vaccine-prices'] })
      toast(price === null ? t('vprice.removed') : t('vprice.saved'))
      setEditing(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const startEdit = (row: VaccinePrice) => {
    setDraft(row.price ?? '')
    setEditing(row.vaccine_code)
  }
  const value = draft.trim()
  const valid = value === '' || FEE_PATTERN.test(value)

  return (
    <Card>
      <div className="border-b border-line px-5 py-3">
        <h2 className="text-sm font-semibold text-tx">{t('vprice.title')}</h2>
        <p className="mt-0.5 text-xs text-tx-3">{t('vprice.subtitle')}</p>
      </div>
      {isLoading ? (
        <PageLoader />
      ) : isError || !data ? (
        <p role="alert" className="px-5 py-6 text-center text-sm text-danger">
          {t('vprice.load_error')}
        </p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>{t('vprice.col_vaccine')}</Th>
              <Th className="text-right">{t('vprice.col_price')}</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => {
              const isEditing = editing === row.vaccine_code
              const name = vaccineName(t, row.vaccine_code)
              return (
                <Tr key={row.vaccine_code}>
                  <Td>
                    <span className="font-medium text-tx">{name}</span>
                    {!row.in_schedule && (
                      <span className="ml-2 text-xs text-tx-3">{t('vax.out_of_scheme')}</span>
                    )}
                  </Td>
                  <Td className="text-right">
                    {isEditing ? (
                      <input
                        aria-label={t('vprice.input').replace('{vaccine}', name)}
                        aria-invalid={!valid}
                        inputMode="decimal"
                        placeholder="—"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        className="h-8 w-24 rounded-md border border-line bg-bg px-2 text-right font-mono text-sm text-tx focus:border-accent focus:outline-none aria-[invalid=true]:border-danger"
                      />
                    ) : row.price !== null ? (
                      <span className="font-mono text-sm text-tx">{fmtFee(row.price)}</span>
                    ) : (
                      <span className="text-xs text-tx-4">{t('vprice.none')}</span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-right">
                    {isEditing ? (
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
                          {t('fee.cancel')}
                        </Button>
                        <Button
                          size="sm"
                          disabled={!valid}
                          loading={save.isPending}
                          onClick={() =>
                            save.mutate({ code: row.vaccine_code, price: value || null })
                          }
                        >
                          {t('fee.save')}
                        </Button>
                      </div>
                    ) : (
                      data.editable && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={editing !== null}
                          aria-label={t('vprice.edit').replace('{vaccine}', name)}
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
        <p>{t('vprice.free_hint')}</p>
        <p>{t('vprice.minsal_note')}</p>
      </div>
    </Card>
  )
}

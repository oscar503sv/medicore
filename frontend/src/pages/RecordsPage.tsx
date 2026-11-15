import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { recordsApi } from '@/api/records'
import { RecordDrawer } from '@/components/records/RecordDrawer'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useDebounced } from '@/lib/useDebounced'
import { useAuthStore } from '@/stores/auth'

export function RecordsPage() {
  const t = useT()
  // The list is metadata for anyone with records.view; only doctors open a record's content.
  const canReadClinical = useAuthStore((s) => s.can('records.read_clinical'))
  const [openId, setOpenId] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [offset, setOffset] = useState(0)
  // Every request is audited server-side, so typing must not fire one per key.
  const search = useDebounced(q.trim(), 300)
  const isFiltered = !!(search || from || to)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['records', 'list', { q: search, from, to, offset }],
    queryFn: () =>
      recordsApi.list({
        q: search || undefined,
        date_from: from || undefined,
        date_to: to || undefined,
        offset,
        limit: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={data ? `${data.total} ${t('records.count_label')}` : undefined}
        title={t('records.title')}
      />

      <div className="flex flex-wrap items-center gap-4">
        <div className="relative w-80">
          <Search
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4"
            aria-hidden="true"
          />
          <input
            type="search"
            aria-label={t('records.search_ph')}
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setOffset(0)
            }}
            maxLength={100}
            placeholder={t('records.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="records-from" className="text-[13px] text-tx-3">
            {t('records.date_from')}
          </label>
          <input
            id="records-from"
            type="date"
            value={from}
            onChange={(e) => {
              setFrom(e.target.value)
              setOffset(0)
            }}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
          <label htmlFor="records-to" className="text-[13px] text-tx-3">
            {t('records.date_to')}
          </label>
          <input
            id="records-to"
            type="date"
            value={to}
            onChange={(e) => {
              setTo(e.target.value)
              setOffset(0)
            }}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
        </div>
        {(q || from || to) && (
          <Button
            variant="outline"
            onClick={() => {
              setQ('')
              setFrom('')
              setTo('')
              setOffset(0)
            }}
          >
            <X className="h-4 w-4" />
            {t('records.clear')}
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : isError ? (
          <div role="alert">
            <EmptyState title={t('records.load_error')} description={errorMessage(error)} />
          </div>
        ) : data && data.items.length > 0 ? (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>{t('records.col_code')}</Th>
                  <Th>{t('records.col_patient')}</Th>
                  <Th>{t('records.col_type')}</Th>
                  <Th>{t('records.col_doctor')}</Th>
                  <Th>{t('records.col_encounter')}</Th>
                  <Th>{t('records.col_status')}</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <Tr key={r.id} onClick={canReadClinical ? () => setOpenId(r.id) : undefined}>
                    <Td>
                      {canReadClinical ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setOpenId(r.id)
                          }}
                          className="rounded font-mono text-[13px] text-tx underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                        >
                          {r.code}
                        </button>
                      ) : (
                        <span className="font-mono text-[13px] text-tx">{r.code}</span>
                      )}
                    </Td>
                    <Td className="font-medium text-tx">{r.patient_name ?? '—'}</Td>
                    <Td>
                      <Badge>{t(`record.type_${r.type}`)}</Badge>
                    </Td>
                    <Td>{r.signed_by_name ?? '—'}</Td>
                    <Td>{fmtDateTz(r.encounter_at)}</Td>
                    <Td>
                      <Badge tone={r.status === 'amended' ? 'info' : 'ok'}>
                        {t(`records.${r.status === 'amended' ? 'amended' : 'signed'}`)}
                      </Badge>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            {data.total > PAGE_SIZE && (
              <Pager
                offset={offset}
                limit={PAGE_SIZE}
                count={data.items.length}
                total={data.total}
                onChange={setOffset}
              />
            )}
          </>
        ) : isFiltered ? (
          <EmptyState title={t('records.title')} description={t('records.empty_filtered')} />
        ) : (
          <EmptyState title={t('records.empty_title')} description={t('records.empty_desc')} />
        )}
      </Card>

      {canReadClinical && <RecordDrawer recordId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}

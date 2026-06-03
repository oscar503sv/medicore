import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { recordsApi } from '@/api/records'
import { RecordDrawer } from '@/components/records/RecordDrawer'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { fmtDateTz } from '@/lib/format'
import { useT } from '@/lib/i18n'

export function RecordsPage() {
  const t = useT()
  const [openId, setOpenId] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['records', 'all'],
    queryFn: () => recordsApi.list(),
  })

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase()
    return (data ?? []).filter((r) => {
      if (
        term &&
        !(r.patient_name ?? '').toLowerCase().includes(term) &&
        !r.chief_complaint.toLowerCase().includes(term)
      )
        return false
      if (from || to) {
        const d = fmtDateTz(r.encounter_at, 'yyyy-MM-dd')
        if (from && d < from) return false
        if (to && d > to) return false
      }
      return true
    })
  }, [data, q, from, to])

  return (
    <div className="space-y-5 p-8">
      <PageHeader eyebrow={`${filtered.length} registros`} title={t('records.title')} />

      <div className="flex flex-wrap items-center gap-4">
        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('records.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[13px] text-tx-3">{t('records.date_from')}</label>
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
          <label className="text-[13px] text-tx-3">{t('records.date_to')}</label>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
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
        ) : filtered.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>{t('records.col_code')}</Th>
                <Th>{t('records.col_patient')}</Th>
                <Th>{t('records.col_reason')}</Th>
                <Th>{t('records.col_type')}</Th>
                <Th>{t('records.col_encounter')}</Th>
                <Th>{t('records.col_status')}</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <Tr key={r.id} onClick={() => setOpenId(r.id)}>
                  <Td>
                    <span className="font-mono text-[13px] text-tx">{r.code}</span>
                  </Td>
                  <Td className="font-medium text-tx">{r.patient_name ?? '—'}</Td>
                  <Td>{r.chief_complaint}</Td>
                  <Td>
                    <Badge>{t(`record.type_${r.type}`)}</Badge>
                  </Td>
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
        ) : data && data.length > 0 ? (
          <EmptyState title={t('records.title')} description={t('records.empty_filtered')} />
        ) : (
          <EmptyState title="Sin historiales" description="Aún no hay registros firmados." />
        )}
      </Card>

      <RecordDrawer recordId={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}

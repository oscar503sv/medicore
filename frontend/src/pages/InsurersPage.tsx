import { useState, type ChangeEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, CheckCircle2, Pencil, Plus, Search, ShieldCheck } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { insurersApi, type InsurerPayload } from '@/api/insurers'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Insurer } from '@/types'

export function InsurersPage() {
  const t = useT()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Insurer | null>(null)
  const [creating, setCreating] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'archived'>('all')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['insurers'],
    queryFn: () => insurersApi.list(),
  })

  const all = data ?? []
  const activeCount = all.filter((i) => i.active).length
  const term = q.trim().toLowerCase()
  const visible = all.filter(
    (i) =>
      (statusFilter === 'all' || (statusFilter === 'active' ? i.active : !i.active)) &&
      (!term ||
        i.name.toLowerCase().includes(term) ||
        (i.contact_person ?? '').toLowerCase().includes(term)),
  )
  const paged = visible.slice(offset, offset + PAGE_SIZE)

  const archive = useMutation({
    mutationFn: (id: string) => insurersApi.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['insurers'] })
      toast(t('insurers.archived_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={`${data?.length ?? 0} ${t('insurers.count')}`}
        title={t('insurers.title')}
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            {t('insurers.new')}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard icon={ShieldCheck} label={t('insurers.stat_total')} value={String(all.length)} />
        <StatCard icon={CheckCircle2} label={t('insurers.stat_active')} value={String(activeCount)} />
        <StatCard icon={Archive} label={t('insurers.stat_archived')} value={String(all.length - activeCount)} />
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setOffset(0)
            }}
            placeholder={t('insurers.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        <Segmented
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v)
            setOffset(0)
          }}
          options={[
            { value: 'all', label: t('app.all') },
            { value: 'active', label: t('insurers.active') },
            { value: 'archived', label: t('insurers.inactive') },
          ]}
        />
      </div>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : visible.length > 0 ? (
          <>
          <Table>
            <thead>
              <tr>
                <Th>{t('insurers.col_name')}</Th>
                <Th>{t('insurers.col_contact')}</Th>
                <Th>{t('insurers.col_address')}</Th>
                <Th>{t('insurers.col_status')}</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {paged.map((ins) => (
                <Tr key={ins.id}>
                  <Td>
                    <p className="font-medium text-tx">{ins.name}</p>
                    {ins.contact_person && (
                      <p className="text-xs text-tx-3">{ins.contact_person}</p>
                    )}
                  </Td>
                  <Td>
                    <p className="text-sm text-tx">{ins.phone ?? '—'}</p>
                    <p className="text-xs text-tx-3">{ins.email ?? ''}</p>
                  </Td>
                  <Td className="max-w-xs truncate text-sm text-tx-2">{ins.address ?? '—'}</Td>
                  <Td>
                    <Badge tone={ins.active ? 'ok' : 'neutral'}>
                      {ins.active ? t('insurers.active') : t('insurers.inactive')}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(ins)}>
                        <Pencil className="h-3.5 w-3.5" />
                        {t('app.edit')}
                      </Button>
                      {ins.active && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => archive.mutate(ins.id)}
                          title={t('insurers.archive')}
                        >
                          <Archive className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          {visible.length > PAGE_SIZE && (
            <Pager offset={offset} limit={PAGE_SIZE} count={paged.length} total={visible.length} onChange={setOffset} />
          )}
          </>
        ) : (
          <EmptyState title={t('insurers.empty_title')} description={t('insurers.empty_desc')} />
        )}
      </Card>

      <InsurerModal
        open={creating || !!editing}
        insurer={editing}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
      />
    </div>
  )
}

const EMPTY: InsurerPayload = {
  name: '',
  phone: '',
  email: '',
  address: '',
  contact_person: '',
  notes: '',
}

function InsurerModal({
  open,
  insurer,
  onClose,
}: {
  open: boolean
  insurer: Insurer | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState<InsurerPayload>(EMPTY)
  // Sync the form with the insurer being edited whenever the modal target changes.
  const [syncedId, setSyncedId] = useState<string | null>(null)
  const targetId = insurer?.id ?? null
  if (open && syncedId !== targetId) {
    setSyncedId(targetId)
    setForm(
      insurer
        ? {
            name: insurer.name,
            phone: insurer.phone ?? '',
            email: insurer.email ?? '',
            address: insurer.address ?? '',
            contact_person: insurer.contact_person ?? '',
            notes: insurer.notes ?? '',
          }
        : EMPTY,
    )
  }

  const save = useMutation({
    mutationFn: () => (insurer ? insurersApi.update(insurer.id, form) : insurersApi.create(form)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['insurers'] })
      toast(insurer ? t('insurers.updated_ok') : t('insurers.created_ok'))
      close()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  function close() {
    setSyncedId(null)
    onClose()
  }

  const set = (k: keyof InsurerPayload) => (e: ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value })

  return (
    <Modal
      open={open}
      onClose={close}
      title={insurer ? t('insurers.edit') : t('insurers.new')}
      width="max-w-lg"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
        className="space-y-4 p-5"
      >
        <Input label={t('insurers.col_name')} value={form.name ?? ''} onChange={set('name')} required />
        <div className="grid grid-cols-2 gap-4">
          <Input label={t('insurers.phone')} value={form.phone ?? ''} onChange={set('phone')} />
          <Input label={t('insurers.email')} type="email" value={form.email ?? ''} onChange={set('email')} />
        </div>
        <Input label={t('insurers.address')} value={form.address ?? ''} onChange={set('address')} />
        <Input
          label={t('insurers.contact_person')}
          value={form.contact_person ?? ''}
          onChange={set('contact_person')}
        />
        <Input label={t('insurers.notes')} value={form.notes ?? ''} onChange={set('notes')} />
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={close}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!form.name}>
            {insurer ? t('app.save') : t('app.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ClipboardList, Pencil, Plus, RotateCcw } from 'lucide-react'
import { errorMessage } from '@/api/client'
import {
  proceduresApi,
  type ProcedurePerformer,
  type ProcedureType,
  type ProcedureTypePayload,
} from '@/api/procedures'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input, Select, Textarea } from '@/components/ui/Input'
import { Menu } from '@/components/ui/Menu'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'

/** Catalog tab (admin): the clinic's procedures, the rules each one carries, archive/restore. */
export function ProcedureCatalog() {
  const t = useT()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<ProcedureType | 'new' | null>(null)
  const { data } = useQuery({ queryKey: ['procedure-catalog'], queryFn: proceduresApi.catalog })

  const toggle = useMutation({
    mutationFn: (k: ProcedureType) => proceduresApi.setTypeActive(k.id, !k.active),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['procedure-catalog'] })
      toast(t('prc.type_saved'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (!data) return <PageLoader />
  return (
    <div>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <p className="text-xs text-tx-3">{t('prc.catalog_hint')}</p>
        <Button size="sm" onClick={() => setEditing('new')}>
          <Plus className="h-4 w-4" />
          {t('prc.catalog_add')}
        </Button>
      </div>
      {data.length === 0 ? (
        <EmptyState icon={ClipboardList} title={t('prc.catalog_add')} />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>{t('prc.col_name')}</Th>
              <Th>{t('prc.col_performer')}</Th>
              <Th>{t('prc.col_consent')}</Th>
              <Th>{t('prc.col_follow_up')}</Th>
              <Th>{t('prc.col_specimen')}</Th>
              <Th>{t('prc.col_state')}</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data.map((k) => (
              <Tr key={k.id}>
                <Td className={k.active ? 'font-medium text-tx' : 'text-tx-3'}>{k.name}</Td>
                <Td className="text-[13px] text-tx-2">{t(`prc.performer.${k.performer}`)}</Td>
                <Td className="text-[13px] text-tx-2">{k.requires_consent ? t('prc.yes') : '—'}</Td>
                <Td className="text-[13px] text-tx-2">
                  {k.follow_up_days ? t('prc.days').replace('{n}', String(k.follow_up_days)) : '—'}
                </Td>
                <Td className="text-[13px] text-tx-2">{k.takes_specimen ? t('prc.yes') : '—'}</Td>
                <Td>
                  <Badge tone={k.active ? 'ok' : 'neutral'}>
                    {k.active ? t('prc.active') : t('prc.archived')}
                  </Badge>
                </Td>
                <Td className="text-right">
                  <Menu
                    label={k.name}
                    items={[
                      { label: t('prc.edit'), icon: Pencil, onSelect: () => setEditing(k) },
                      k.active
                        ? {
                            label: t('prc.archive'),
                            icon: Archive,
                            tone: 'danger' as const,
                            onSelect: () => toggle.mutate(k),
                          }
                        : {
                            label: t('prc.restore'),
                            icon: RotateCcw,
                            onSelect: () => toggle.mutate(k),
                          },
                    ]}
                  />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      <ProcedureTypeModal kind={editing} onClose={() => setEditing(null)} />
    </div>
  )
}

const EMPTY = {
  name: '',
  performer: 'doctor' as ProcedurePerformer,
  requires_consent: false,
  follow_up_days: '',
  takes_specimen: false,
  technique_template: '',
  instructions_template: '',
}

function ProcedureTypeModal({
  kind,
  onClose,
}: {
  kind: ProcedureType | 'new' | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState(EMPTY)
  const set = (patch: Partial<typeof EMPTY>) => setForm((f) => ({ ...f, ...patch }))

  useEffect(() => {
    if (!kind) return
    setForm(
      kind === 'new'
        ? EMPTY
        : {
            name: kind.name,
            performer: kind.performer,
            requires_consent: kind.requires_consent,
            follow_up_days: kind.follow_up_days ? String(kind.follow_up_days) : '',
            takes_specimen: kind.takes_specimen,
            technique_template: kind.technique_template ?? '',
            instructions_template: kind.instructions_template ?? '',
          },
    )
  }, [kind])

  const save = useMutation({
    mutationFn: () => {
      const payload: ProcedureTypePayload = {
        name: form.name.trim(),
        performer: form.performer,
        requires_consent: form.requires_consent,
        follow_up_days: Number(form.follow_up_days) || null,
        takes_specimen: form.takes_specimen,
        technique_template: form.technique_template.trim() || null,
        instructions_template: form.instructions_template.trim() || null,
      }
      return kind === 'new' || !kind
        ? proceduresApi.createType(payload)
        : proceduresApi.updateType(kind.id, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['procedure-catalog'] })
      toast(t('prc.type_saved'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal
      open={kind !== null}
      onClose={onClose}
      title={kind === 'new' ? t('prc.type_new') : t('prc.type_edit')}
      width="max-w-2xl"
    >
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <div className="grid gap-4 sm:grid-cols-[1.6fr_1fr]">
          <Input
            label={t('prc.name')}
            value={form.name}
            onChange={(e) => set({ name: e.target.value })}
            required
          />
          <Select
            label={t('prc.who')}
            value={form.performer}
            onChange={(e) => set({ performer: e.target.value as ProcedurePerformer })}
          >
            <option value="doctor">{t('prc.performer.doctor')}</option>
            <option value="doctor_or_nurse">{t('prc.performer.doctor_or_nurse')}</option>
          </Select>
        </div>
        <div className="grid items-end gap-4 sm:grid-cols-[180px_1fr]">
          <Input
            type="number"
            min={1}
            max={365}
            label={t('prc.follow_up_days')}
            value={form.follow_up_days}
            placeholder="—"
            onChange={(e) => set({ follow_up_days: e.target.value })}
          />
          <p className="pb-2.5 text-xs text-tx-3">{t('prc.follow_up_days_hint')}</p>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <label className="flex items-center gap-2 text-sm text-tx-2">
            <Checkbox
              checked={form.requires_consent}
              onChange={(e) => set({ requires_consent: e.target.checked })}
            />
            {t('prc.requires_consent')}
          </label>
          <label className="flex items-center gap-2 text-sm text-tx-2">
            <Checkbox
              checked={form.takes_specimen}
              onChange={(e) => set({ takes_specimen: e.target.checked })}
            />
            {t('prc.takes_specimen')}
          </label>
        </div>
        <Textarea
          label={t('prc.technique_template')}
          rows={3}
          value={form.technique_template}
          onChange={(e) => set({ technique_template: e.target.value })}
        />
        <Textarea
          label={t('prc.instructions_template')}
          rows={3}
          value={form.instructions_template}
          onChange={(e) => set({ instructions_template: e.target.value })}
        />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!form.name.trim()}>
            {t('prc.save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { noteTemplatesApi } from '@/api/noteTemplates'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { NoteCatalog, NoteRole, NoteTemplate, SectionInput } from '@/types'

const ROLES: NoteRole[] = [
  'problems',
  'subjective',
  'history',
  'objective',
  'assessment',
  'plan',
  'free',
]
const MAX_SECTIONS = 12

/**
 * The clinic's own note templates (plans with custom templates). Each section has a type
 * (role) so text follows it when switching formats and the plan feeds the prescription.
 * Editing never changes notes already written: they keep the version they used.
 */
export function CustomNoteTemplates({ catalog }: { catalog: NoteCatalog }) {
  const t = useT()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<NoteTemplate | 'new' | null>(null)
  const [deleting, setDeleting] = useState<NoteTemplate | null>(null)
  const custom = catalog.templates.filter((tpl) => !tpl.system)

  const archive = useMutation({
    mutationFn: (key: string) => noteTemplatesApi.archive(key),
    onSuccess: (c) => {
      qc.setQueryData(['note-catalog'], c)
      toast(t('note.custom.deleted'))
      setDeleting(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Card>
      <CardHeader
        title={t('note.custom.title')}
        action={
          catalog.custom_allowed && (
            <Button size="sm" onClick={() => setEditing('new')}>
              <Plus className="h-4 w-4" />
              {t('note.custom.new')}
            </Button>
          )
        }
      />
      <div className="space-y-4 p-5">
        {!catalog.custom_allowed ? (
          <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-tx-2">
            {t('note.custom.upsell')}
          </p>
        ) : (
          <>
            <p className="text-[13px] text-tx-3">{t('note.custom.desc')}</p>
            {custom.length === 0 ? (
              <p className="text-sm text-tx-4">{t('note.custom.empty')}</p>
            ) : (
              <ul className="divide-y divide-line rounded-lg border border-line">
                {custom.map((tpl) => (
                  <li key={tpl.key} className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-tx">{tpl.name}</p>
                      <p className="truncate text-xs text-tx-3">
                        {tpl.sections.map((s) => s.title).join(' · ')}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setEditing(tpl)}
                      aria-label={t('note.custom.edit')}
                      className="rounded-md p-1.5 text-tx-3 hover:bg-surface-2 hover:text-tx"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleting(tpl)}
                      aria-label={t('app.delete')}
                      className="rounded-md p-1.5 text-tx-3 hover:bg-surface-2 hover:text-danger"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
      {editing && (
        <TemplateEditor
          template={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={deleting?.name ?? ''}>
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('note.custom.delete_confirm')}</p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleting(null)}>
              {t('app.cancel')}
            </Button>
            <Button
              variant="danger"
              loading={archive.isPending}
              onClick={() => deleting && archive.mutate(deleting.key)}
            >
              {t('app.delete')}
            </Button>
          </div>
        </div>
      </Modal>
    </Card>
  )
}

function TemplateEditor({
  template,
  onClose,
}: {
  template: NoteTemplate | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const [name, setName] = useState(template?.name ?? '')
  const [sections, setSections] = useState<SectionInput[]>(
    template?.sections.map(({ title, role, required }) => ({ title, role, required })) ?? [
      { title: '', role: 'subjective', required: true },
      { title: '', role: 'objective', required: true },
      { title: '', role: 'plan', required: true },
    ],
  )

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: name.trim(),
        sections: sections.map((s) => ({ ...s, title: s.title.trim() })),
      }
      return template
        ? noteTemplatesApi.update(template.key, payload)
        : noteTemplatesApi.create(payload)
    },
    onSuccess: (c) => {
      qc.setQueryData(['note-catalog'], c)
      toast(t('note.custom.saved'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const update = (i: number, patch: Partial<SectionInput>) =>
    setSections((cur) => cur.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const move = (i: number, by: -1 | 1) =>
    setSections((cur) => {
      const next = [...cur]
      ;[next[i], next[i + by]] = [next[i + by], next[i]]
      return next
    })
  const valid = name.trim() && sections.length > 0 && sections.every((s) => s.title.trim())

  return (
    <Modal
      open
      onClose={onClose}
      title={template ? t('note.custom.edit') : t('note.custom.new')}
      width="max-w-2xl"
    >
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          if (valid) save.mutate()
        }}
      >
        <Input
          label={t('note.custom.name')}
          value={name}
          maxLength={80}
          placeholder={t('note.custom.name_ph')}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <div>
          <p className="mb-2 text-[13px] font-medium text-tx-2">{t('note.custom.sections')}</p>
          <ol className="space-y-2">
            {sections.map((s, i) => (
              <li
                key={i}
                className="grid grid-cols-1 items-center gap-2 rounded-lg border border-line p-3 sm:grid-cols-[1fr_190px_auto_auto]"
              >
                <input
                  value={s.title}
                  maxLength={80}
                  onChange={(e) => update(i, { title: e.target.value })}
                  placeholder={t('note.custom.section_title')}
                  aria-label={t('note.custom.section_title')}
                  className="h-9 w-full rounded-lg border border-line bg-bg px-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
                />
                <Select
                  aria-label={t('note.custom.role')}
                  value={s.role}
                  onChange={(e) => update(i, { role: e.target.value as NoteRole })}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`note.role.${r}`)}
                    </option>
                  ))}
                </Select>
                <label className="flex items-center gap-1.5 text-xs text-tx-2">
                  <Checkbox
                    checked={s.required}
                    onChange={(e) => update(i, { required: e.target.checked })}
                  />
                  {t('note.custom.required')}
                </label>
                <div className="flex items-center">
                  <IconButton
                    label={t('note.custom.move_up')}
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                  >
                    <ArrowUp className="h-4 w-4" />
                  </IconButton>
                  <IconButton
                    label={t('note.custom.move_down')}
                    disabled={i === sections.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    <ArrowDown className="h-4 w-4" />
                  </IconButton>
                  <IconButton
                    label={t('note.custom.remove_section')}
                    disabled={sections.length === 1}
                    onClick={() => setSections((cur) => cur.filter((_, j) => j !== i))}
                  >
                    <Trash2 className="h-4 w-4" />
                  </IconButton>
                </div>
              </li>
            ))}
          </ol>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="mt-2"
            disabled={sections.length >= MAX_SECTIONS}
            onClick={() =>
              setSections((cur) => [...cur, { title: '', role: 'free', required: false }])
            }
          >
            <Plus className="h-4 w-4" />
            {t('note.custom.add_section')}
          </Button>
        </div>
        {template && <p className="text-xs text-tx-3">{t('note.custom.edit_hint')}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!valid}>
            {t('app.save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded-md p-1.5 text-tx-3 hover:bg-surface-2 hover:text-tx disabled:opacity-30"
    >
      {children}
    </button>
  )
}

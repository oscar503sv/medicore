import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import { noteTemplatesApi } from '@/api/noteTemplates'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Select } from '@/components/ui/Select'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { CustomNoteTemplates } from '@/components/settings/CustomNoteTemplates'
import { templateName } from '@/lib/notes'
import { useAuthStore } from '@/stores/auth'
import type { NoteCatalog, NoteSettings } from '@/types'

const RULES = ['first_visit', 'consult', 'follow_up', 'check_up', 'procedure', 'emergency']

/**
 * Clinical note formats: the doctor's preferred one and, for whoever configures the clinic
 * (the admin, or the doctor in a single-doctor plan), which formats are available, the
 * default, the format per kind of visit and whether it is mandatory.
 */
export function NoteTemplatesSection() {
  // Only doctors write notes (an admin may hold the consultation permissions too).
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const { data: catalog } = useQuery({
    queryKey: ['note-catalog'],
    queryFn: noteTemplatesApi.catalog,
  })
  if (!catalog) return <PageLoader />
  return (
    <>
      {/* A doctor who configures the formats (single-doctor plan) sets the default itself */}
      {isDoctor && !catalog.can_configure && <FavouriteCard catalog={catalog} />}
      {catalog.can_configure && <ClinicNotesCard catalog={catalog} solo={isDoctor} />}
      {catalog.can_configure && <CustomNoteTemplates catalog={catalog} />}
    </>
  )
}

function FavouriteCard({ catalog }: { catalog: NoteCatalog }) {
  const t = useT()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (template: string | null) => noteTemplatesApi.setFavourite(template),
    onSuccess: (c) => {
      qc.setQueryData(['note-catalog'], c)
      toast(t('note.favourite_saved'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const locked = catalog.settings.locked
  return (
    <Card>
      <CardHeader title={t('note.settings.favourite')} />
      <div className="space-y-3 p-5">
        <p className="text-[13px] text-tx-3">
          {locked ? t('note.settings.favourite_locked') : t('note.settings.favourite_hint')}
        </p>
        <Select
          aria-label={t('note.settings.favourite')}
          value={catalog.favourite ?? ''}
          disabled={locked || save.isPending}
          onChange={(e) => save.mutate(e.target.value || null)}
          className="max-w-sm"
        >
          <option value="">{t('note.settings.favourite_none')}</option>
          {catalog.templates
            .filter((tpl) => catalog.allowed.includes(tpl.key))
            .map((tpl) => (
              <option key={tpl.key} value={tpl.key}>
                {templateName(t, tpl.key, tpl.name)}
              </option>
            ))}
        </Select>
      </div>
    </Card>
  )
}

function ClinicNotesCard({ catalog, solo }: { catalog: NoteCatalog; solo: boolean }) {
  const t = useT()
  const qc = useQueryClient()
  const all = catalog.templates.map((tpl) => tpl.key)
  const fromCatalog = (c: NoteCatalog): NoteSettings => ({
    ...c.settings,
    enabled: c.settings.enabled.length ? c.settings.enabled : all,
  })
  const [draft, setDraft] = useState<NoteSettings>(() => fromCatalog(catalog))
  useEffect(() => setDraft(fromCatalog(catalog)), [catalog]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () =>
      noteTemplatesApi.updateSettings({
        ...draft,
        // Every format enabled is stored as "all", so formats added later are included.
        enabled: draft.enabled.length === all.length ? [] : draft.enabled,
      }),
    onSuccess: (c) => {
      qc.setQueryData(['note-catalog'], c)
      toast(t('note.settings.saved'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const toggle = (key: string, on: boolean) => {
    setDraft((d) => {
      const enabled = on
        ? all.filter((k) => k === key || d.enabled.includes(k))
        : d.enabled.filter((k) => k !== key)
      if (enabled.length === 0) return d // at least one format
      const rules = Object.fromEntries(
        Object.entries(d.rules).filter(([, v]) => enabled.includes(v)),
      )
      return { ...d, enabled, rules, default: enabled.includes(d.default) ? d.default : enabled[0] }
    })
  }

  return (
    <Card>
      <CardHeader title={t('note.settings.title')} />
      <div className="space-y-6 p-5">
        <p className="text-[13px] text-tx-3">
          {solo ? t('note.settings.desc_solo') : t('note.settings.desc')}
        </p>

        <div>
          <p className="mb-2 text-[13px] font-medium text-tx-2">{t('note.settings.enabled')}</p>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {catalog.templates.map((tpl) => {
              const on = draft.enabled.includes(tpl.key)
              const isDefault = draft.default === tpl.key
              return (
                <li key={tpl.key} className="flex items-start gap-3 px-4 py-3">
                  <Checkbox
                    checked={on}
                    onChange={(e) => toggle(tpl.key, e.target.checked)}
                    aria-label={templateName(t, tpl.key, tpl.name)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-tx">{templateName(t, tpl.key, tpl.name)}</p>
                    <p className="truncate text-xs text-tx-3">
                      {tpl.system
                        ? t(`note.template_desc.${tpl.key}`)
                        : tpl.sections.map((s) => s.title).join(' · ')}
                    </p>
                  </div>
                  {isDefault ? (
                    <span className="shrink-0 rounded-pill bg-[var(--accent-10)] px-2 py-0.5 text-xs text-accent">
                      {t('note.settings.default')}
                    </span>
                  ) : (
                    on && (
                      <button
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, default: tpl.key }))}
                        className="shrink-0 text-xs text-tx-3 hover:text-accent"
                      >
                        {t('note.settings.make_default')}
                      </button>
                    )
                  )}
                </li>
              )
            })}
          </ul>
        </div>

        <div>
          <p className="text-[13px] font-medium text-tx-2">{t('note.settings.rules')}</p>
          <p className="mb-3 text-xs text-tx-3">{t('note.settings.rules_hint')}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {RULES.map((rule) => (
              <Select
                key={rule}
                label={
                  rule === 'first_visit'
                    ? t('note.settings.rule.first_visit')
                    : t(`apptype.${rule}`)
                }
                value={draft.rules[rule] ?? ''}
                onChange={(e) =>
                  setDraft((d) => {
                    const rules = { ...d.rules }
                    if (e.target.value) rules[rule] = e.target.value
                    else delete rules[rule]
                    return { ...d, rules }
                  })
                }
              >
                <option value="">
                  {solo || draft.locked
                    ? t('note.settings.no_rule_solo')
                    : t('note.settings.no_rule')}
                </option>
                {catalog.templates
                  .filter((tpl) => draft.enabled.includes(tpl.key))
                  .map((tpl) => (
                    <option key={tpl.key} value={tpl.key}>
                      {templateName(t, tpl.key, tpl.name)}
                    </option>
                  ))}
              </Select>
            ))}
          </div>
        </div>

        {!solo && (
          <label className="flex items-start gap-2.5">
            <Checkbox
              checked={draft.locked}
              onChange={(e) => setDraft((d) => ({ ...d, locked: e.target.checked }))}
              className="mt-0.5"
            />
            <span>
              <span className="block text-sm text-tx">{t('note.settings.locked')}</span>
              <span className="block text-xs text-tx-3">{t('note.settings.locked_hint')}</span>
            </span>
          </label>
        )}

        <div className="flex justify-end">
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            {t('app.save')}
          </Button>
        </div>
      </div>
    </Card>
  )
}

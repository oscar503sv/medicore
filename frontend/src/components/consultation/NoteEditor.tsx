import { Check, Lock, Star } from 'lucide-react'
import { Select } from '@/components/ui/Select'
import { useT } from '@/lib/i18n'
import { roleLetter, sectionHint, sectionTitle, templateName } from '@/lib/notes'
import type { ClinicalNote, NoteCatalog } from '@/types'

/**
 * The clinical note of the live consultation, in the template it opened with. The doctor
 * can switch to another template the clinic allows (unless the clinic made its format
 * mandatory) and mark it as their preferred one. Sections lay out two per row; the first
 * one spans the row when the count is odd (P-SOAP's problems, the history's anamnesis) and
 * a free-text note takes the full width.
 */
export function NoteEditor({
  note,
  texts,
  catalog,
  switching,
  onChange,
  onSwitch,
  onFavourite,
}: {
  note: ClinicalNote
  texts: Record<string, string>
  catalog: NoteCatalog | undefined
  switching: boolean
  onChange: (key: string, text: string) => void
  onSwitch: (template: string) => void
  onFavourite: (template: string | null) => void
}) {
  const t = useT()
  const locked = catalog?.settings.locked ?? false
  const options = (catalog?.templates ?? []).filter(
    (tpl) => catalog?.allowed.includes(tpl.key) || tpl.key === note.template,
  )
  const isFavourite = catalog?.favourite === note.template
  const odd = note.sections.length % 2 === 1

  return (
    <section id="sec-note" className="scroll-mt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-tx">{t('note.title')}</h3>
        <div className="flex items-center gap-2">
          {locked ? (
            <span
              className="inline-flex items-center gap-1.5 rounded-pill border border-line px-2.5 py-1 text-xs text-tx-2"
              title={t('note.locked')}
            >
              <Lock className="h-3 w-3 text-tx-4" />
              {templateName(t, note.template, note.name)}
            </span>
          ) : (
            <>
              <Select
                aria-label={t('note.template')}
                value={note.template}
                disabled={switching || options.length < 2}
                onChange={(e) => onSwitch(e.target.value)}
                className="w-64"
              >
                {options.map((tpl) => (
                  <option key={tpl.key} value={tpl.key}>
                    {templateName(t, tpl.key, tpl.name)}
                  </option>
                ))}
              </Select>
              <button
                type="button"
                onClick={() => onFavourite(isFavourite ? null : note.template)}
                title={isFavourite ? t('note.favourite_on') : t('note.favourite')}
                aria-label={isFavourite ? t('note.favourite_on') : t('note.favourite')}
                aria-pressed={isFavourite}
                className="rounded-md p-1.5 text-tx-4 hover:bg-surface-2 hover:text-warn"
              >
                <Star className={`h-4 w-4 ${isFavourite ? 'fill-warn text-warn' : ''}`} />
              </button>
            </>
          )}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {note.sections.map((s, i) => {
          const value = texts[s.key] ?? ''
          const filled = value.trim().length > 0
          const free = s.role === 'free'
          const wide = free || (odd && i === 0)
          const hint = sectionHint(t, note.template, s.key)
          return (
            <div
              key={s.key}
              className={`rounded-xl border border-line bg-surface p-4 ${wide ? 'sm:col-span-2' : ''}`}
            >
              <div className="mb-2 flex items-start gap-2.5">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-surface-2 font-serif text-sm text-accent">
                  {roleLetter(s.role)}
                </span>
                <div className="min-w-0 flex-1">
                  <label htmlFor={`note-${s.key}`} className="flex items-center gap-2">
                    <span className="text-sm font-medium text-tx">
                      {sectionTitle(t, note.template, s)}
                    </span>
                    {!s.required && (
                      <span className="text-[11px] text-tx-4">{t('note.optional')}</span>
                    )}
                    {filled && <Check className="h-3.5 w-3.5 text-ok" aria-hidden />}
                  </label>
                  {hint && <p className="text-xs leading-snug text-tx-3">{hint}</p>}
                </div>
              </div>
              <textarea
                id={`note-${s.key}`}
                value={value}
                onChange={(e) => onChange(s.key, e.target.value)}
                rows={free ? 12 : 4}
                placeholder={t('app.write_here')}
                className={`w-full resize-y rounded-lg border border-line bg-bg p-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none ${
                  free ? 'min-h-[260px]' : 'min-h-[112px]'
                }`}
              />
            </div>
          )
        })}
      </div>
    </section>
  )
}

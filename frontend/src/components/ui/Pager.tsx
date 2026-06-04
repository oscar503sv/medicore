import { Button } from '@/components/ui/Button'
import { useT } from '@/lib/i18n'

export const PAGE_SIZE = 25

/** Inline pager: "{from}–{to} / {total}" with Prev/Next. Works for server- and client-side
 *  pagination (pass count = rows shown on the current page, total = full result size). */
export function Pager({
  offset,
  limit,
  count,
  total,
  onChange,
}: {
  offset: number
  limit: number
  count: number
  total: number
  onChange: (next: number) => void
}) {
  const t = useT()
  const start = total === 0 ? 0 : offset + 1
  const end = offset + count
  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[13px] text-tx-3">
      <span>{`${start}–${end} / ${total}`}</span>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          {t('audit.prev')}
        </Button>
        <Button variant="outline" size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          {t('audit.next')}
        </Button>
      </div>
    </div>
  )
}

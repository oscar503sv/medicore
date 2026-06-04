import { useT } from '@/lib/i18n'

// Keys already surfaced elsewhere (Detail column / support badge) — hidden from the raw dump.
const HIDDEN = new Set(['subject', 'impersonated_by'])

/** Expanded-row content: the full audit metadata as key/value pairs, plus the user agent. */
export function AuditMetadata({
  metadata,
  userAgent,
}: {
  metadata?: Record<string, unknown> | null
  userAgent?: string | null
}) {
  const t = useT()
  const entries = Object.entries(metadata ?? {}).filter(([k]) => !HIDDEN.has(k))

  if (entries.length === 0 && !userAgent)
    return <p className="text-[13px] text-tx-3">{t('audit.no_detail')}</p>

  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2">
          <dt className="font-mono text-tx-3">{key}</dt>
          <dd className="break-all text-tx-2">{String(value)}</dd>
        </div>
      ))}
      {userAgent && (
        <div className="flex gap-2 sm:col-span-2">
          <dt className="font-mono text-tx-3">user_agent</dt>
          <dd className="break-all text-tx-2">{userAgent}</dd>
        </div>
      )}
    </dl>
  )
}

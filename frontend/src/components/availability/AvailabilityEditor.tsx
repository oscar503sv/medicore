import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { AvailabilityScope } from '@/api/availability'
import { errorMessage } from '@/api/client'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { ExceptionsTab } from './ExceptionsTab'
import { PreviewTab } from './PreviewTab'
import { RulesEditor } from './RulesEditor'
import { blocksMinutes } from './schedule'
import { WeeklyEditor } from './WeeklyEditor'

type Tab = 'weekly' | 'exceptions' | 'rules' | 'preview'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-tx-3">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-tx">{value}</p>
    </Card>
  )
}

/**
 * Schedule editor (weekly hours, exceptions, booking rules, preview) for one scope: the
 * signed-in doctor's own availability or a service agenda's.
 */
export function AvailabilityEditor({
  scope,
  scopeKey,
}: {
  scope: AvailabilityScope
  /** Identifies the scope in the query cache. */
  scopeKey: string
}) {
  const t = useT()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('weekly')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['availability', scopeKey],
    queryFn: scope.get,
  })

  if (isLoading) return <PageLoader />
  if (isError || !data)
    return (
      <p role="alert" className="px-5 py-8 text-center text-sm text-danger">
        {t('avail.load_error')}
      </p>
    )

  const save = async (action: () => Promise<unknown>, okKey: string) => {
    try {
      await action()
      qc.invalidateQueries({ queryKey: ['availability'] })
      toast(t(okKey))
    } catch (err) {
      toast(errorMessage(err), 'danger')
    }
  }

  const activeDays = data.weekly.filter((d) => d.enabled).length
  const weekMinutes = data.weekly.reduce(
    (sum, d) => sum + (d.enabled ? blocksMinutes(d.blocks) : 0),
    0,
  )

  const tabs: { id: Tab; label: string }[] = [
    { id: 'weekly', label: t('avail.weekly') },
    { id: 'exceptions', label: `${t('avail.exceptions')} · ${data.exceptions.length}` },
    { id: 'rules', label: t('avail.rules') },
    { id: 'preview', label: t('avail.preview') },
  ]

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label={t('avail.hours_week')}
          value={`${(weekMinutes / 60).toFixed(weekMinutes % 60 ? 1 : 0)}h`}
        />
        <Stat label={t('avail.active_days')} value={`${activeDays}/7`} />
        <Stat label={t('avail.default_slot')} value={`${data.rules.slot_minutes} min`} />
        <Stat label={t('avail.exceptions')} value={`${data.exceptions.length}`} />
      </div>

      <div role="tablist" className="flex gap-1 border-b border-line">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            type="button"
            role="tab"
            aria-selected={tab === tb.id}
            onClick={() => setTab(tb.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
              tab === tb.id
                ? 'border-accent text-accent'
                : 'border-transparent text-tx-3 hover:text-tx',
            )}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {tab === 'weekly' && (
        <WeeklyEditor
          weekly={data.weekly}
          onSave={(weekly) => save(() => scope.updateWeekly(weekly), 'avail.weekly_saved')}
        />
      )}
      {tab === 'exceptions' && <ExceptionsTab exceptions={data.exceptions} scope={scope} />}
      {tab === 'rules' && (
        <RulesEditor
          rules={data.rules}
          onSave={(rules) => save(() => scope.updateRules(rules), 'avail.rules_saved')}
        />
      )}
      {tab === 'preview' && <PreviewTab scope={scope} scopeKey={scopeKey} />}
    </div>
  )
}

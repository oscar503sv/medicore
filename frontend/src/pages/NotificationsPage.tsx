import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO, subDays } from 'date-fns'
import { BellOff, Check, CheckCheck } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { notificationsApi, type NotificationCategory } from '@/api/notifications'
import { PageHeader } from '@/components/PageHeader'
import { TONE_TEXT } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { clinicToday, fmtDateTz, fmtRelative, fmtTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { describeNotification } from '@/lib/notifications'
import type { AppNotification } from '@/types'

const PAGE = 30
type Status = 'all' | 'unread'
type CategoryFilter = 'all' | NotificationCategory

/** Full inbox: every notification of the last 90 days, filterable and grouped by day. */
export function NotificationsPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [status, setStatus] = useState<Status>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['notifications', 'inbox', { status, category }],
    queryFn: ({ pageParam }) =>
      notificationsApi.list({
        unread_only: status === 'unread',
        category: category === 'all' ? undefined : category,
        offset: pageParam,
        limit: PAGE,
      }),
    initialPageParam: 0,
    // A full page means there may be more; offsets keep counting from what's loaded.
    getNextPageParam: (last, pages) =>
      last.items.length === PAGE ? pages.length * PAGE : undefined,
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })

  const markRead = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: refresh,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const markAll = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: refresh,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const items = data?.pages.flatMap((p) => p.items) ?? []
  const unread = data?.pages[0]?.unread_count ?? 0
  const filtered = status !== 'all' || category !== 'all'

  const open = (n: AppNotification, href: string | null) => {
    if (!n.read_at) markRead.mutate(n.id)
    if (href) navigate(href)
  }

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={t('notif.inbox')}
        title={t('notif.title')}
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => markAll.mutate()}
            disabled={unread === 0}
            loading={markAll.isPending}
          >
            <CheckCheck className="h-4 w-4" />
            {t('notif.mark_all')}
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Segmented<Status>
          value={status}
          onChange={setStatus}
          options={[
            { value: 'all', label: t('notif.filter_all') },
            { value: 'unread', label: t('notif.filter_unread') },
          ]}
        />
        <Segmented<CategoryFilter>
          value={category}
          onChange={setCategory}
          options={[
            { value: 'all', label: t('notif.filter_all') },
            { value: 'appointment', label: t('notif.cat.appointment') },
            { value: 'record', label: t('notif.cat.record') },
            { value: 'document', label: t('notif.cat.document') },
            { value: 'application', label: t('notif.cat.application') },
            { value: 'procedure', label: t('notif.cat.procedure') },
            { value: 'user', label: t('notif.cat.user') },
          ]}
        />
        <span className="ml-auto text-[13px] text-tx-3">
          {t('notif.unread_count').replace('{n}', String(unread))}
        </span>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <PageLoader />
        ) : items.length === 0 ? (
          <EmptyState
            icon={BellOff}
            title={filtered ? t('notif.empty_filtered') : t('notif.empty')}
            description={t('notif.retention')}
          />
        ) : (
          <>
            {groupByDay(items).map(([day, group]) => (
              <section key={day}>
                <h2 className="border-b border-line-soft bg-surface-2/60 px-5 py-2 text-xs font-medium uppercase tracking-wide text-tx-3">
                  {dayLabel(t, day, group[0].created_at)}
                </h2>
                <ul className="divide-y divide-line-soft">
                  {group.map((n) => (
                    <Row
                      key={n.id}
                      n={n}
                      onOpen={open}
                      onMarkRead={() => markRead.mutate(n.id)}
                    />
                  ))}
                </ul>
              </section>
            ))}
            {hasNextPage && (
              <div className="border-t border-line-soft p-3 text-center">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => fetchNextPage()}
                  loading={isFetchingNextPage}
                >
                  {t('notif.load_more')}
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}

function Row({
  n,
  onOpen,
  onMarkRead,
}: {
  n: AppNotification
  onOpen: (n: AppNotification, href: string | null) => void
  onMarkRead: () => void
}) {
  const t = useT()
  const view = describeNotification(t, n)
  const Icon = view.icon
  return (
    <li className={cn('group flex items-start gap-3 px-5 py-3.5', !n.read_at && 'bg-[var(--accent-10)]')}>
      <button
        onClick={() => onOpen(n, view.href)}
        className="flex min-w-0 flex-1 items-start gap-3 text-left"
      >
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-pill bg-surface-2">
          <Icon className={cn('h-4 w-4', TONE_TEXT[view.tone])} />
        </span>
        <span className="min-w-0 flex-1">
          <span className={cn('block text-sm', n.read_at ? 'text-tx-2' : 'font-medium text-tx')}>
            {view.text}
          </span>
          <span className="mt-0.5 block text-xs text-tx-3">
            {fmtTimeTz(n.created_at)} · {fmtRelative(n.created_at)}
          </span>
        </span>
      </button>
      {!n.read_at && (
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={onMarkRead}
            className="rounded-md p-1.5 text-tx-3 opacity-0 transition-opacity hover:bg-surface-2 hover:text-tx focus:opacity-100 group-hover:opacity-100"
            title={t('notif.mark_read')}
            aria-label={t('notif.mark_read')}
          >
            <Check className="h-4 w-4" />
          </button>
          <span className="h-2 w-2 rounded-pill bg-accent" />
        </div>
      )}
    </li>
  )
}

/** Consecutive notifications grouped by their day in the clinic's timezone (newest first). */
function groupByDay(items: AppNotification[]): [string, AppNotification[]][] {
  const groups: [string, AppNotification[]][] = []
  for (const n of items) {
    const day = fmtDateTz(n.created_at, 'yyyy-MM-dd')
    const last = groups[groups.length - 1]
    if (last && last[0] === day) last[1].push(n)
    else groups.push([day, [n]])
  }
  return groups
}

function dayLabel(t: (key: string) => string, day: string, sample: string): string {
  const today = clinicToday()
  if (day === today) return t('notif.today')
  if (day === format(subDays(parseISO(today), 1), 'yyyy-MM-dd')) return t('notif.yesterday')
  return fmtDateTz(sample, t('notif.day_pattern'))
}

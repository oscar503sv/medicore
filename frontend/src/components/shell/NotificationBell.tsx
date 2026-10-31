import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { notificationsApi } from '@/api/notifications'
import { TONE_TEXT } from '@/components/ui/badgeTone'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtRelative } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { describeNotification } from '@/lib/notifications'
import type { AppNotification } from '@/types'

const PAGE = 20
// Polling is enough for a clinic: a new notification shows up within a minute.
const POLL_MS = 60_000

export function NotificationBell() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [limit, setLimit] = useState(PAGE)

  const { data: unread = 0 } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: POLL_MS,
    staleTime: 0,
  })

  const { data: list, isLoading } = useQuery({
    // `unread` in the key: a new arrival picked up by the poll refreshes an open list too.
    queryKey: ['notifications', 'list', { unreadOnly, limit, unread }],
    queryFn: () => notificationsApi.list({ unread_only: unreadOnly, limit }),
    enabled: open,
    staleTime: 0,
    placeholderData: keepPreviousData,
  })

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })

  const markRead = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: refresh,
  })

  const markAll = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: refresh,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const close = () => {
    setOpen(false)
    setLimit(PAGE)
  }

  const onSelect = (n: AppNotification, href: string | null) => {
    if (!n.read_at) markRead.mutate(n.id)
    if (href) {
      close()
      navigate(href)
    }
  }

  const items = list?.items ?? []
  const badge = unread > 9 ? '9+' : String(unread)

  return (
    <div className="relative">
      <button
        onClick={() => (open ? close() : setOpen(true))}
        className="relative rounded-md p-2 text-tx-2 hover:bg-surface-2"
        title={t('notif.title')}
        aria-label={t('notif.open')}
        aria-expanded={open}
      >
        <Bell className="h-[18px] w-[18px]" />
        {unread > 0 && (
          <span className="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-pill bg-accent px-1 text-[10px] font-semibold leading-none text-white">
            {badge}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={close} />
          <div className="absolute right-0 top-11 z-20 flex max-h-[min(32rem,80vh)] w-96 flex-col rounded-lg border border-line bg-surface shadow-lg animate-pop-in">
            <div className="flex items-center justify-between gap-2 border-b border-line-soft px-4 py-3">
              <p className="text-sm font-medium text-tx">{t('notif.title')}</p>
              <div className="flex items-center gap-3">
                <label className="flex cursor-pointer items-center gap-1.5 text-xs text-tx-3">
                  <input
                    type="checkbox"
                    checked={unreadOnly}
                    onChange={(e) => {
                      setUnreadOnly(e.target.checked)
                      setLimit(PAGE)
                    }}
                    className="accent-[var(--accent)]"
                  />
                  {t('notif.unread_only')}
                </label>
                <button
                  onClick={() => markAll.mutate()}
                  disabled={unread === 0 || markAll.isPending}
                  className="rounded-md p-1 text-tx-3 hover:bg-surface-2 hover:text-tx disabled:opacity-40 disabled:hover:bg-transparent"
                  title={t('notif.mark_all')}
                  aria-label={t('notif.mark_all')}
                >
                  <CheckCheck className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : items.length === 0 ? (
                <p className="px-4 py-10 text-center text-sm text-tx-3">{t('notif.empty')}</p>
              ) : (
                <ul className="divide-y divide-line-soft">
                  {items.map((n) => {
                    const view = describeNotification(t, n)
                    const Icon = view.icon
                    return (
                      <li key={n.id}>
                        <button
                          onClick={() => onSelect(n, view.href)}
                          className={cn(
                            'flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2',
                            !n.read_at && 'bg-[var(--accent-10)]',
                          )}
                        >
                          <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', TONE_TEXT[view.tone])} />
                          <span className="min-w-0 flex-1">
                            <span className={cn('block text-[13px]', n.read_at ? 'text-tx-2' : 'text-tx')}>
                              {view.text}
                            </span>
                            <span className="mt-0.5 block text-xs text-tx-3">
                              {fmtRelative(n.created_at)}
                            </span>
                          </span>
                          {!n.read_at && (
                            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-pill bg-accent" />
                          )}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
              {items.length === limit && (
                <button
                  onClick={() => setLimit((l) => l + PAGE)}
                  className="w-full border-t border-line-soft py-2.5 text-xs font-medium text-accent hover:bg-surface-2"
                >
                  {t('notif.load_more')}
                </button>
              )}
            </div>
            <button
              onClick={() => {
                close()
                navigate('/notifications')
              }}
              className="border-t border-line-soft py-2.5 text-center text-xs font-medium text-accent hover:bg-surface-2"
            >
              {t('notif.view_all')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

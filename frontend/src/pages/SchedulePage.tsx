import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { addDays, format, parseISO, startOfWeek } from 'date-fns'
import { appointmentsApi, type BookingDoctor } from '@/api/appointments'
import { PageHeader } from '@/components/PageHeader'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Select } from '@/components/ui/Input'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { cn } from '@/lib/cn'
import { clinicNowTime, clinicToday, fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Appointment } from '@/types'

/** Pixels per hour: a 30-minute appointment gets 44 px — room for two readable lines. */
const HOUR_PX = 88
const DEFAULT_FIRST_HOUR = 8
const DEFAULT_LAST_HOUR = 19

/** Colour per status (CSS variable) — the card's left border and a light tint over the surface. */
const STATUS_COLOR: Record<string, string> = {
  scheduled: '--info',
  confirmed: '--accent',
  in_progress: '--warn',
  completed: '--ok',
  cancelled: '--danger',
  no_show: '--danger',
}
const LEGEND = ['scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled'] as const
const INACTIVE = new Set(['cancelled', 'no_show'])

const minutesOf = (iso: string) => {
  const d = parseISO(iso)
  return d.getHours() * 60 + d.getMinutes()
}

type View = 'week' | 'day'

/** A grid column: a weekday (week view) or a doctor (day view). */
interface Column {
  key: string
  date: string
  header: ReactNode
  appts: Appointment[]
  onHeaderClick?: () => void
  headerTitle?: string
}

export function SchedulePage() {
  const t = useT()
  const navigate = useNavigate()
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const canManage = useAuthStore((s) => s.can('appointments.manage'))
  const sessionName = useAuthStore((s) => s.session?.name)
  const today = clinicToday()
  // View + date live in the URL so reloads, links and the back button keep them.
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'day' ? 'day' : 'week'
  const date = /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') ?? '') ? params.get('date')! : today
  const go = (next: { view?: View; date?: string }) =>
    setParams({ view: next.view ?? view, date: next.date ?? date }, { replace: true })

  const [doctorId, setDoctorId] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const weekStart = startOfWeek(parseISO(date), { weekStartsOn: 1 })
  const weekStartStr = format(weekStart, 'yyyy-MM-dd')

  // The day view reads the same weekly payload (shared cache when switching views).
  const { data: schedule, isLoading } = useQuery({
    queryKey: ['schedule', weekStartStr, doctorId],
    queryFn: () => appointmentsApi.weeklySchedule(weekStartStr, doctorId || undefined),
  })

  // Doctors only ever see their own agenda; the filter is for the front desk / admins.
  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
    enabled: canManage && !isDoctor,
  })
  const doctors = options?.doctors ?? []

  const days = Array.from({ length: 7 }, (_, i) => format(addDays(weekStart, i), 'yyyy-MM-dd'))
  const byDay = useMemo(() => {
    const out: Record<string, Appointment[]> = {}
    for (const [day, appts] of Object.entries(schedule ?? {})) {
      out[day] = showInactive ? appts : appts.filter((a) => !INACTIVE.has(a.status))
    }
    return out
  }, [schedule, showInactive])

  const columns: Column[] =
    view === 'week'
      ? days.map((day) => ({
          key: day,
          date: day,
          appts: byDay[day] ?? [],
          onHeaderClick: () => go({ view: 'day', date: day }),
          headerTitle: t('sched.open_day'),
          header: <DayHeader day={day} today={today} count={byDay[day]?.length ?? 0} />,
        }))
      : dayColumns(
          byDay[date] ?? [],
          date,
          // A single agenda: the doctor's own, or the one picked in the filter.
          isDoctor
            ? (sessionName ?? null)
            : doctorId
              ? (doctors.find((d) => d.id === doctorId)?.name ?? null)
              : undefined,
          doctors,
          setDoctorId,
          t('sched.only_doctor'),
        )

  // The visible range grows to fit early/late appointments (e.g. an 18:30 slot ends at 19:00).
  const all = columns.flatMap((c) => c.appts)
  const firstHour = Math.min(
    DEFAULT_FIRST_HOUR,
    ...all.map((a) => Math.floor(minutesOf(a.scheduled_start) / 60)),
  )
  const lastHour = Math.min(
    24,
    Math.max(DEFAULT_LAST_HOUR, ...all.map((a) => Math.ceil(minutesOf(a.scheduled_end) / 60))),
  )
  const hours = Array.from({ length: lastHour - firstHour }, (_, i) => firstHour + i)
  const toPx = (minutes: number) => ((minutes - firstHour * 60) * HOUR_PX) / 60

  const now = useNow()
  const nowMinutes = Number(now.slice(0, 2)) * 60 + Number(now.slice(3))
  const showNow = nowMinutes >= firstHour * 60 && nowMinutes <= lastHour * 60
  const total = all.length
  const step = view === 'week' ? 7 : 1
  const shift = (n: number) => go({ date: format(addDays(parseISO(date), n), 'yyyy-MM-dd') })
  const grid = {
    gridTemplateColumns: `60px repeat(${columns.length}, minmax(${view === 'day' ? 200 : 0}px, 1fr))`,
  }

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t(view === 'week' ? 'appt.week_view' : 'sched.day_view')}
        action={
          <div className="flex flex-wrap items-center justify-end gap-3">
            <Segmented<View>
              value={view}
              onChange={(v) => go({ view: v })}
              options={[
                { value: 'day', label: t('sched.view_day') },
                { value: 'week', label: t('sched.view_week') },
              ]}
            />
            {doctors.length > 0 && (
              <Select
                value={doctorId}
                onChange={(e) => setDoctorId(e.target.value)}
                className="h-9 w-56"
                aria-label={t('sched.doctor')}
              >
                <option value="">{t('sched.all_doctors')}</option>
                {doctors.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            )}
            <Button variant="outline" size="sm" onClick={() => go({ date: today })}>
              {t(view === 'week' ? 'sched.this_week' : 'sched.today')}
            </Button>
            <div className="flex items-center">
              <button
                onClick={() => shift(-step)}
                className="rounded-md p-2 text-tx-2 hover:bg-surface-2"
                aria-label={t(view === 'week' ? 'sched.prev_week' : 'sched.prev_day')}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="min-w-[150px] text-center text-sm font-medium text-tx first-letter:uppercase">
                {view === 'week'
                  ? `${fmtDate(days[0], 'd MMM')} – ${fmtDate(days[6], 'd MMM yyyy')}`
                  : fmtDate(date, t('sched.day_pattern'))}
              </span>
              <button
                onClick={() => shift(step)}
                className="rounded-md p-2 text-tx-2 hover:bg-surface-2"
                aria-label={t(view === 'week' ? 'sched.next_week' : 'sched.next_day')}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-tx-2">
        {LEGEND.map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ background: `var(${STATUS_COLOR[s]})` }}
            />
            {t(`status.${s}`)}
          </span>
        ))}
        <label className="ml-auto flex cursor-pointer items-center gap-2">
          <Checkbox checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          {t('sched.show_inactive')}
        </label>
        <span className="text-tx-3">
          {t(view === 'week' ? 'sched.week_total' : 'sched.day_total').replace(
            '{n}',
            String(total),
          )}
        </span>
      </div>

      {isLoading ? (
        <PageLoader />
      ) : (
        <Card className="overflow-hidden">
          <div className="max-h-[calc(100vh-240px)] overflow-auto">
            {/* Column headers (sticky while scrolling the hours) */}
            <div className="sticky top-0 z-20 grid border-b border-line bg-surface" style={grid}>
              <div />
              {columns.map((c) => (
                <div
                  key={c.key}
                  role={c.onHeaderClick ? 'button' : undefined}
                  tabIndex={c.onHeaderClick ? 0 : undefined}
                  onClick={c.onHeaderClick}
                  onKeyDown={(e) => e.key === 'Enter' && c.onHeaderClick?.()}
                  title={c.headerTitle}
                  className={cn(
                    'border-l border-line px-2 py-2.5',
                    c.onHeaderClick && 'cursor-pointer hover:bg-surface-2',
                    view === 'week' && c.date === today && 'bg-[var(--accent-10)]',
                  )}
                >
                  {c.header}
                </div>
              ))}
            </div>

            <div className="relative grid" style={grid}>
              {/* Hour labels */}
              <div>
                {hours.map((h) => (
                  <div
                    key={h}
                    style={{ height: HOUR_PX }}
                    className="border-b border-line-soft pr-2 pt-1.5 text-right"
                  >
                    <span className="font-mono text-[11px] text-tx-3">
                      {String(h).padStart(2, '0')}:00
                    </span>
                  </div>
                ))}
              </div>

              {columns.map((c) => {
                const isToday = c.date === today
                return (
                  <div
                    key={c.key}
                    className="relative border-l border-line"
                    style={
                      isToday && view === 'week'
                        ? {
                            background: 'color-mix(in oklab, var(--accent) 4%, transparent)',
                          }
                        : undefined
                    }
                  >
                    {hours.map((h) => (
                      <div
                        key={h}
                        style={{ height: HOUR_PX }}
                        className="relative border-b border-line-soft"
                      >
                        <div className="absolute inset-x-0 top-1/2 border-t border-dashed border-line-soft" />
                      </div>
                    ))}

                    {layoutDay(c.appts).map((it) => {
                      const box = {
                        top: toPx(it.start) + 1,
                        height: Math.max(((it.end - it.start) * HOUR_PX) / 60 - 2, 20),
                        left: `calc(${(it.lane / it.lanes) * 100}% + 3px)`,
                        width: `calc(${100 / it.lanes}% - 6px)`,
                      }
                      // Week → zoom into that day; day → the appointment list to act on it.
                      const open = () =>
                        view === 'week'
                          ? go({ view: 'day', date: c.date })
                          : navigate(`/appointments?date=${c.date}`)
                      return it.appts.length === 1 ? (
                        <AppointmentCard
                          key={it.key}
                          a={it.appts[0]}
                          box={box}
                          detailed={view === 'day'}
                          showDoctor={view === 'week' && !isDoctor && !doctorId}
                          onOpen={open}
                        />
                      ) : (
                        <GroupCard key={it.key} appts={it.appts} box={box} onOpen={open} />
                      )
                    })}

                    {isToday && showNow && (
                      <div
                        className="pointer-events-none absolute inset-x-0 z-10 flex items-center"
                        style={{ top: toPx(nowMinutes) }}
                      >
                        <span className="-ml-1 h-2 w-2 rounded-full bg-danger" />
                        <span className="h-px flex-1 bg-danger" />
                      </div>
                    )}
                  </div>
                )
              })}

              {view === 'day' && all.length === 0 && (
                <div className="pointer-events-none absolute inset-0 flex items-start justify-center pt-24">
                  <span className="rounded-pill border border-line bg-surface px-4 py-2 text-sm text-tx-3 shadow-sm">
                    {t('sched.no_appts_day')}
                  </span>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}

function DayHeader({ day, today, count }: { day: string; today: string; count: number }) {
  const isToday = day === today
  return (
    <div className="flex items-center justify-center gap-2">
      <span
        className={cn(
          'text-[11px] font-medium uppercase tracking-wide',
          isToday ? 'text-accent' : 'text-tx-3',
        )}
      >
        {fmtDate(day, 'EEE')}
      </span>
      <span
        className={cn(
          'flex h-7 min-w-7 items-center justify-center rounded-pill px-1 text-sm font-semibold',
          isToday ? 'bg-accent text-white' : 'text-tx',
        )}
      >
        {fmtDate(day, 'd')}
      </span>
      {count > 0 && (
        <span className="rounded-pill bg-surface-2 px-1.5 text-[11px] text-tx-3">{count}</span>
      )}
    </div>
  )
}

function DoctorHeader({
  name,
  specialty,
  count,
}: {
  name: string
  specialty?: string | null
  count: number
}) {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <Avatar name={name} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-tx">{name}</p>
        {specialty && <p className="truncate text-[11px] text-tx-3">{specialty}</p>}
      </div>
      {count > 0 && (
        <span className="rounded-pill bg-surface-2 px-1.5 text-[11px] text-tx-3">{count}</span>
      )}
    </div>
  )
}

/**
 * Day view columns: one per doctor for the front desk (every bookable doctor, so free
 * agendas show too), a single column when the agenda is already one doctor's.
 */
function dayColumns(
  appts: Appointment[],
  date: string,
  /** undefined → one column per doctor; otherwise a single agenda (name, if known). */
  single: string | null | undefined,
  doctors: BookingDoctor[],
  pickDoctor: (id: string) => void,
  onlyDoctorTitle: string,
): Column[] {
  if (single !== undefined) {
    const name = single ?? appts[0]?.doctor_name
    return [
      {
        key: 'single',
        date,
        appts,
        header: name ? (
          <DoctorHeader name={name} count={appts.length} />
        ) : (
          <DayHeader day={date} today="" count={appts.length} />
        ),
      },
    ]
  }
  const known = new Map(doctors.map((d) => [d.id, { name: d.name, specialty: d.specialty }]))
  for (const a of appts) {
    if (!known.has(a.doctor_id))
      known.set(a.doctor_id, { name: a.doctor_name ?? '—', specialty: null })
  }
  if (known.size === 0)
    return [
      {
        key: 'empty',
        date,
        appts: [],
        header: <DayHeader day={date} today="" count={0} />,
      },
    ]
  return [...known.entries()]
    .sort(([, x], [, y]) => x.name.localeCompare(y.name))
    .map(([id, d]) => {
      const own = appts.filter((a) => a.doctor_id === id)
      return {
        key: id,
        date,
        appts: own,
        onHeaderClick: doctors.length > 0 ? () => pickDoctor(id) : undefined,
        headerTitle: doctors.length > 0 ? onlyDoctorTitle : undefined,
        header: <DoctorHeader name={d.name} specialty={d.specialty} count={own.length} />,
      }
    })
}

interface Box {
  top: number
  height: number
  left: string
  width: string
}

function AppointmentCard({
  a,
  box,
  detailed,
  showDoctor,
  onOpen,
}: {
  a: Appointment
  box: Box
  /** Day view: wide columns leave room for the end time, status and type. */
  detailed: boolean
  showDoctor: boolean
  onOpen: () => void
}) {
  const t = useT()
  const color = `var(${STATUS_COLOR[a.status] ?? '--line'})`
  const inactive = INACTIVE.has(a.status)
  const time = format(parseISO(a.scheduled_start), 'HH:mm')
  const compact = box.height < 38
  const name = a.patient_name ?? a.reason
  const tooltip = [
    `${time}–${format(parseISO(a.scheduled_end), 'HH:mm')} · ${t(`status.${a.status}`)}`,
    a.patient_name,
    a.reason,
    a.doctor_name,
  ]
    .filter(Boolean)
    .join('\n')

  return (
    <button
      onClick={onOpen}
      title={tooltip}
      className={cn(
        'absolute overflow-hidden rounded-md border-l-[3px] px-2 text-left shadow-sm transition',
        'hover:z-10 hover:shadow-md focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        compact ? 'flex items-center gap-1.5 py-0.5' : 'py-1',
        inactive && 'opacity-60',
      )}
      style={{
        ...box,
        borderLeftColor: color,
        background: `color-mix(in oklab, ${color} 13%, var(--surface))`,
      }}
    >
      {compact ? (
        <p className={cn('truncate text-[12px] text-tx', inactive && 'line-through')}>
          <span className="font-mono text-tx-3">{time}</span>{' '}
          <span className="font-medium">{name}</span>
        </p>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <p
              className={cn(
                'min-w-0 flex-1 truncate text-[12.5px] font-medium leading-tight text-tx',
                inactive && 'line-through',
              )}
            >
              {name}
            </p>
            {detailed && (
              <span className="shrink-0 text-[11px] font-medium leading-tight" style={{ color }}>
                {t(`status.${a.status}`)}
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-[11.5px] leading-tight text-tx-2">
            <span className="font-mono">
              {time}
              {detailed && `–${format(parseISO(a.scheduled_end), 'HH:mm')}`}
            </span>{' '}
            · {a.reason}
            {detailed && <span className="text-tx-3"> · {t(`apptype.${a.type}`)}</span>}
          </p>
          {showDoctor && box.height >= 62 && a.doctor_name && (
            <p className="mt-0.5 truncate text-[11px] leading-tight text-tx-3">{a.doctor_name}</p>
          )}
        </>
      )}
    </button>
  )
}

/** Several appointments at the same time (all-doctors view), summarized in one card. */
function GroupCard({ appts, box, onOpen }: { appts: Appointment[]; box: Box; onOpen: () => void }) {
  const t = useT()
  const time = format(parseISO(appts[0].scheduled_start), 'HH:mm')
  const names = appts.map((a) => (a.patient_name ?? a.reason).split(' ')[0])
  const tooltip = appts
    .map(
      (a) =>
        `${format(parseISO(a.scheduled_start), 'HH:mm')} · ${a.patient_name ?? a.reason}` +
        (a.doctor_name ? ` — ${a.doctor_name}` : ''),
    )
    .join('\n')
  return (
    <button
      onClick={onOpen}
      title={tooltip}
      className={cn(
        'absolute overflow-hidden rounded-md border border-line bg-surface px-2 py-1 text-left shadow-sm transition',
        'hover:z-10 hover:shadow-md focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
      )}
      style={box}
    >
      <p className="flex items-center gap-1.5 text-[12.5px] font-medium leading-tight text-tx">
        <span className="flex -space-x-0.5">
          {appts.slice(0, 6).map((a) => (
            <span
              key={a.id}
              className="h-2 w-2 rounded-full ring-1 ring-[var(--surface)]"
              style={{
                background: `var(${STATUS_COLOR[a.status] ?? '--line'})`,
              }}
            />
          ))}
        </span>
        {t('sched.group').replace('{n}', String(appts.length))}
      </p>
      <p className="mt-0.5 truncate text-[11.5px] leading-tight text-tx-2">
        <span className="font-mono">{time}</span> · {names.join(', ')}
      </p>
    </button>
  )
}

interface Item {
  key: string
  start: number
  end: number
  appts: Appointment[]
}
interface Placed extends Item {
  lane: number
  lanes: number
}

/** Side-by-side lanes allowed before overlaps collapse into a group card (narrow = unreadable). */
const MAX_LANES = 1

/**
 * Layout for overlapping appointments (e.g. several doctors at 10:00 in the all-doctors
 * view). Overlaps are split into side-by-side lanes; when a cluster would need more than
 * MAX_LANES, its appointments are bucketed by start time into "N appointments" cards.
 */
function layoutDay(appts: Appointment[]): Placed[] {
  const items = appts.map((a) => ({
    key: a.id,
    start: minutesOf(a.scheduled_start),
    end: minutesOf(a.scheduled_end),
    appts: [a],
  }))
  return clusters(items).flatMap((cluster) => {
    const placed = assignLanes(cluster)
    if (placed[0].lanes <= MAX_LANES) return placed
    const buckets = new Map<number, Item>()
    for (const it of cluster) {
      const b = buckets.get(it.start)
      if (b) {
        b.appts.push(...it.appts)
        b.end = Math.max(b.end, it.end)
      } else {
        buckets.set(it.start, {
          ...it,
          key: `g-${it.start}`,
          appts: [...it.appts],
        })
      }
    }
    return clusters([...buckets.values()]).flatMap(assignLanes)
  })
}

/** Groups items (sorted by start) into runs of transitively overlapping intervals. */
function clusters(items: Item[]): Item[][] {
  const sorted = [...items].sort((x, y) => x.start - y.start || x.end - y.end)
  const out: Item[][] = []
  let end = -1
  for (const it of sorted) {
    if (it.start >= end) out.push([])
    out[out.length - 1].push(it)
    end = Math.max(end, it.end)
  }
  return out
}

function assignLanes(cluster: Item[]): Placed[] {
  const laneEnds: number[] = []
  const placed = cluster.map((it) => {
    let lane = laneEnds.findIndex((e) => e <= it.start)
    if (lane === -1) lane = laneEnds.push(it.end) - 1
    else laneEnds[lane] = it.end
    return { ...it, lane, lanes: 1 }
  })
  for (const p of placed) p.lanes = laneEnds.length
  return placed
}

/** Clinic wall-clock time (HH:mm), refreshed every minute for the "now" line. */
function useNow() {
  const [now, setNow] = useState(clinicNowTime)
  useEffect(() => {
    const id = setInterval(() => setNow(clinicNowTime()), 60_000)
    return () => clearInterval(id)
  }, [])
  return now
}

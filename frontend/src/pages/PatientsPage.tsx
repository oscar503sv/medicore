import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { addDays, format, parseISO } from 'date-fns'
import {
  AlertTriangle,
  CalendarCheck,
  CalendarPlus,
  Phone,
  Plus,
  Search,
  UserPlus,
  Users,
  UserX,
} from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { patientsApi } from '@/api/patients'
import { NewAppointmentModal } from '@/components/appointments/NewAppointmentModal'
import { PageHeader } from '@/components/PageHeader'
import { NewPatientModal } from '@/components/patients/NewPatientModal'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Select } from '@/components/ui/Input'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { cn } from '@/lib/cn'
import { clinicToday, fmtDate, fmtRelative } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Patient } from '@/types'

type StatusFilter = 'active' | 'inactive' | 'all'
const MAX_TAGS = 2

export function PatientsPage() {
  const t = useT()
  const navigate = useNavigate()
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const userId = useAuthStore((s) => s.session?.user_id)
  const canBook = useAuthStore((s) => s.can('appointments.manage'))
  const [q, setQ] = useState('')
  const search = useDebounced(q.trim(), 250)
  const [status, setStatus] = useState<StatusFilter>('active')
  // Doctors: "all" or "mine" (patients they're the primary doctor of); others: a doctor id.
  const [doctorId, setDoctorId] = useState('')
  const [offset, setOffset] = useState(0)
  const [modalOpen, setModalOpen] = useState(false)
  const [bookFor, setBookFor] = useState<Patient | null>(null)

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['patients', { search, status, doctorId, offset }],
    queryFn: () =>
      patientsApi.list({
        q: search || undefined,
        status: status === 'all' ? undefined : status,
        doctor_id: doctorId || undefined,
        offset,
        limit: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData, // no flash of the loader while typing
  })

  // Headline numbers, independent of the table's filters.
  const { data: stats } = useQuery({
    queryKey: ['patients', 'stats'],
    queryFn: patientsApi.stats,
  })

  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
    enabled: canBook && !isDoctor,
  })
  const doctors = options?.doctors ?? []
  const doctorNames = new Map(doctors.map((d) => [d.id, d.name]))

  const reset = () => setOffset(0)
  const filtered = !!search || !!doctorId || status !== 'active'
  const registered = stats ? stats.active + stats.inactive : null

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={
          registered != null
            ? t('patients.registered').replace('{n}', String(registered))
            : undefined
        }
        title={t('patients.title')}
        action={
          <Button onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            {t('patients.new')}
          </Button>
        }
      />

      <div
        className={cn(
          'grid grid-cols-2 gap-4',
          stats?.with_upcoming != null ? 'sm:grid-cols-4' : 'sm:grid-cols-3',
        )}
      >
        <StatCard icon={Users} label={t('patients.active')} value={String(stats?.active ?? '—')} />
        <StatCard
          icon={UserPlus}
          label={t('patients.stat_new')}
          value={String(stats?.new_recent ?? '—')}
        />
        {stats?.with_upcoming != null && (
          <StatCard
            icon={CalendarCheck}
            label={t('patients.stat_upcoming')}
            value={String(stats.with_upcoming)}
          />
        )}
        <StatCard
          icon={UserX}
          label={t('patients.inactive')}
          value={String(stats?.inactive ?? '—')}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-96">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              reset()
            }}
            placeholder={t('patients.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        {isDoctor && userId ? (
          <Segmented
            value={doctorId ? 'mine' : 'all'}
            onChange={(v) => {
              setDoctorId(v === 'mine' ? userId : '')
              reset()
            }}
            options={[
              { value: 'all', label: t('app.all') },
              { value: 'mine', label: t('patients.mine') },
            ]}
          />
        ) : (
          doctors.length > 0 && (
            <Select
              value={doctorId}
              onChange={(e) => {
                setDoctorId(e.target.value)
                reset()
              }}
              className="w-72"
              aria-label={t('patients.col_doctor')}
            >
              <option value="">{t('patients.any_doctor')}</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          )
        )}
        <div className="ml-auto">
          <Segmented<StatusFilter>
            value={status}
            onChange={(v) => {
              setStatus(v)
              reset()
            }}
            options={[
              { value: 'active', label: t('patients.active') },
              { value: 'inactive', label: t('patients.inactive') },
              { value: 'all', label: t('app.all') },
            ]}
          />
        </div>
      </div>

      <Card className={cn('transition-opacity', isFetching && !isLoading && 'opacity-70')}>
        {isLoading ? (
          <PageLoader />
        ) : data && data.items.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>{t('patients.col_patient')}</Th>
                <Th>{t('patients.col_age')}</Th>
                <Th>{t('patients.col_contact')}</Th>
                <Th>{t('patients.col_tags')}</Th>
                <Th>{t('patients.col_last')}</Th>
                <Th>{t('patients.col_next')}</Th>
                {canBook && <Th />}
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <PatientRow
                  key={p.id}
                  p={p}
                  doctorName={
                    !isDoctor && p.primary_doctor_id
                      ? doctorNames.get(p.primary_doctor_id)
                      : undefined
                  }
                  canBook={canBook}
                  onOpen={() => navigate(`/patients/${p.id}`)}
                  onBook={() => setBookFor(p)}
                />
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            title={filtered ? t('patients.empty_filtered') : t('patients.empty_title')}
            description={filtered ? undefined : t('patients.empty_desc')}
            action={
              !filtered ? (
                <Button size="sm" onClick={() => setModalOpen(true)}>
                  <Plus className="h-4 w-4" />
                  {t('patients.new')}
                </Button>
              ) : undefined
            }
          />
        )}
        {data && data.total > PAGE_SIZE && (
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={data.items.length}
            total={data.total}
            onChange={setOffset}
          />
        )}
      </Card>

      <NewPatientModal open={modalOpen} onClose={() => setModalOpen(false)} />
      <NewAppointmentModal
        open={!!bookFor}
        onClose={() => setBookFor(null)}
        date={clinicToday()}
        initialPatient={bookFor}
      />
    </div>
  )
}

function PatientRow({
  p,
  doctorName,
  canBook,
  onOpen,
  onBook,
}: {
  p: Patient
  doctorName?: string
  canBook: boolean
  onOpen: () => void
  onBook: () => void
}) {
  const t = useT()
  const name = `${p.first_name} ${p.last_name}`
  const inactive = p.status === 'inactive'
  const extraTags = p.tags.slice(MAX_TAGS)

  return (
    <Tr onClick={onOpen} className={cn('group', inactive && 'opacity-60')}>
      <Td>
        <div className="flex items-center gap-3">
          <Avatar name={name} size="sm" />
          <div className="min-w-0">
            <p className="flex items-center gap-2 font-medium text-tx">
              {name}
              {p.allergies.length > 0 && (
                <span
                  className="text-danger"
                  title={t('patients.allergies_title').replace('{list}', p.allergies.join(', '))}
                  aria-label={t('patients.allergies_title').replace(
                    '{list}',
                    p.allergies.join(', '),
                  )}
                >
                  <AlertTriangle className="h-3.5 w-3.5" />
                </span>
              )}
              {inactive && <Badge tone="neutral">{t('patients.inactive')}</Badge>}
            </p>
            <p className="font-mono text-xs text-tx-3">
              {p.code}
              {doctorName && <span className="font-sans"> · {doctorName}</span>}
            </p>
          </div>
        </div>
      </Td>
      <Td className="whitespace-nowrap">
        <span title={t(`sex.${p.sex}`)}>
          {p.age} · {t(`patients.sex_short.${p.sex}`)}
        </span>
      </Td>
      <Td className="whitespace-nowrap">
        {p.contact.phone ? (
          <span className="inline-flex items-center gap-1.5 text-tx-2">
            <Phone className="h-3.5 w-3.5 text-tx-4" />
            {p.contact.phone}
          </span>
        ) : (
          <span className="text-tx-4">—</span>
        )}
      </Td>
      <Td>
        <div className="flex flex-wrap items-center gap-1">
          {p.tags.slice(0, MAX_TAGS).map((tag) => (
            <Badge key={tag} tone="accent">
              {tag}
            </Badge>
          ))}
          {extraTags.length > 0 && (
            <span className="text-xs text-tx-3" title={extraTags.join(', ')}>
              +{extraTags.length}
            </span>
          )}
        </div>
      </Td>
      <Td className="whitespace-nowrap">
        {p.last_visit ? (
          <>
            <p className="text-tx-2">{fmtDate(p.last_visit)}</p>
            <p className="text-xs text-tx-3">{fmtRelative(p.last_visit)}</p>
          </>
        ) : (
          <span className="text-tx-4">{t('patients.never')}</span>
        )}
      </Td>
      <Td className="whitespace-nowrap">
        <NextVisit iso={p.next_visit} />
      </Td>
      {canBook && (
        <Td className="text-right">
          {!inactive && (
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation() // the row opens the chart
                onBook()
              }}
              className="opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100"
            >
              <CalendarPlus className="h-3.5 w-3.5" />
              {t('patients.book')}
            </Button>
          )}
        </Td>
      )}
    </Tr>
  )
}

/** "Hoy · 09:30" / "Mañana · 11:00" for the next two days, the date otherwise. */
function NextVisit({ iso }: { iso: string | null }) {
  const t = useT()
  if (!iso) return <span className="text-tx-4">—</span>
  const day = iso.slice(0, 10)
  const today = clinicToday()
  const tomorrow = format(addDays(parseISO(today), 1), 'yyyy-MM-dd')
  const time = format(parseISO(iso), 'HH:mm')
  if (day === today || day === tomorrow) {
    return (
      <span className="font-medium text-accent">
        {t(day === today ? 'dash.today' : 'dash.tomorrow')} · {time}
      </span>
    )
  }
  return (
    <span className="text-tx-2">
      {fmtDate(iso, 'd MMM')} · {time}
    </span>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

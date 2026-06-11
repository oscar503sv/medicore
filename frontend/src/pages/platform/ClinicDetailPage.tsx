import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, KeyRound, LogIn, Pencil } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformTenantsApi } from '@/api/platform'
import { useAuthStore } from '@/stores/auth'
import type { Permission, PermissionsMatrix, Role, User } from '@/types'
import { PageHeader } from '@/components/PageHeader'
import { PermissionsMatrixTable } from '@/components/permissions/PermissionsMatrixTable'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { statusTone } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { TIMEZONES } from '@/lib/timezones'
import { Activity, CalendarCheck, FileText, Search, Users } from 'lucide-react'
import type { TenantStatus } from '@/types'

function genPassword(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
  return Array.from({ length: 12 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

const STATUS_TONE: Record<TenantStatus, 'ok' | 'danger' | 'neutral'> = {
  active: 'ok',
  suspended: 'danger',
  archived: 'neutral',
}

export function ClinicDetailPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { id = '' } = useParams()

  const { data: clinic, isLoading } = useQuery({
    queryKey: ['platform-tenant', id],
    queryFn: () => platformTenantsApi.get(id),
  })

  const [legalName, setLegalName] = useState('')
  const [taxId, setTaxId] = useState('')
  const [plan, setPlan] = useState('')
  const [seatLimit, setSeatLimit] = useState(10)
  const [icdVersion, setIcdVersion] = useState('cie11')
  const [timezone, setTimezone] = useState('America/El_Salvador')
  const [locationName, setLocationName] = useState('')

  useEffect(() => {
    if (clinic) {
      setLegalName(clinic.legal_name)
      setTaxId(clinic.tax_id)
      setPlan(clinic.plan)
      setSeatLimit(clinic.seat_limit)
      setIcdVersion(clinic.icd_version)
      setTimezone(clinic.timezone)
      const primary = clinic.locations.find((l) => l.is_primary) ?? clinic.locations[0]
      setLocationName(primary?.name ?? '')
    }
  }, [clinic])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['platform-tenant', id] })
    qc.invalidateQueries({ queryKey: ['platform-tenants'] })
  }

  const save = useMutation({
    mutationFn: () =>
      platformTenantsApi.update(id, {
        legal_name: legalName,
        tax_id: taxId,
        plan,
        seat_limit: seatLimit,
        icd_version: icdVersion,
        timezone,
        location_name: locationName,
      }),
    onSuccess: () => {
      toast(t('platform.saved_ok'))
      invalidate()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const setStatus = useMutation({
    mutationFn: (status: string) => platformTenantsApi.setStatus(id, status),
    onSuccess: () => {
      toast(t('platform.status_changed_ok'))
      invalidate()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const { data: stats } = useQuery({
    queryKey: ['platform-tenant-stats', id],
    queryFn: () => platformTenantsApi.tenantStats(id),
  })

  const { data: users } = useQuery({
    queryKey: ['platform-tenant-users', id],
    queryFn: () => platformTenantsApi.listUsers(id),
  })

  const [userQ, setUserQ] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [offset, setOffset] = useState(0)
  const [editTarget, setEditTarget] = useState<User | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null)
  const [supportOpen, setSupportOpen] = useState(false)
  const [supportReason, setSupportReason] = useState('')
  const filteredUsers = useMemo(() => {
    const term = userQ.trim().toLowerCase()
    return (users?.items ?? []).filter((u) => {
      if (term && !u.name.toLowerCase().includes(term) && !u.email.toLowerCase().includes(term))
        return false
      if (roleFilter !== 'all' && u.role !== roleFilter) return false
      if (statusFilter !== 'all' && u.status !== statusFilter) return false
      return true
    })
  }, [users, userQ, roleFilter, statusFilter])
  const pagedUsers = filteredUsers.slice(offset, offset + PAGE_SIZE)

  const resetPassword = useMutation({
    mutationFn: (userId: string) => platformTenantsApi.resetUserPassword(id, userId, genPassword()),
    onSuccess: (res, userId) => {
      const u = res.items.find((x) => x.id === userId)
      toast(`${t('platform.password_reset_ok')} · ${u?.email}`)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const reactivate = useMutation({
    mutationFn: (userId: string) => platformTenantsApi.unlockUser(id, userId),
    onSuccess: () => {
      toast(t('users.activated_ok'))
      qc.invalidateQueries({ queryKey: ['platform-tenant-users', id] })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const suspend = useMutation({
    mutationFn: (userId: string) => platformTenantsApi.suspendUser(id, userId),
    onSuccess: () => {
      toast(t('users.deactivated_ok'))
      qc.invalidateQueries({ queryKey: ['platform-tenant-users', id] })
      setDeactivateTarget(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const impersonate = useMutation({
    mutationFn: (reason: string) => platformTenantsApi.impersonate(id, reason),
    onSuccess: (s) => {
      useAuthStore.getState().setSession({
        user_id: s.user_id,
        tenant_id: s.tenant_id,
        tenant_name: s.tenant_name,
        timezone: s.timezone,
        role: s.role as Role,
        name: s.name,
        sex: null,
        must_change_password: false,
        permissions: s.permissions,
        impersonating: true,
      })
      navigate('/')
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const { data: permMatrix } = useQuery({
    queryKey: ['platform-tenant-permissions', id],
    queryFn: () => platformTenantsApi.getPermissions(id),
  })
  const refreshPerms = (next: PermissionsMatrix) => {
    qc.setQueryData(['platform-tenant-permissions', id], next)
    toast(t('permissions.saved'))
  }
  const savePerms = useMutation({
    mutationFn: ({ role, permissions }: { role: Role; permissions: Permission[] }) =>
      platformTenantsApi.updateRolePermissions(id, role, permissions),
    onSuccess: refreshPerms,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const resetPerms = useMutation({
    mutationFn: (role: Role) => platformTenantsApi.resetRolePermissions(id, role),
    onSuccess: refreshPerms,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !clinic) return <PageLoader />

  // Save stays disabled until the clinic info actually changes.
  const primaryName = (clinic.locations.find((l) => l.is_primary) ?? clinic.locations[0])?.name ?? ''
  const dirty =
    legalName !== clinic.legal_name ||
    taxId !== clinic.tax_id ||
    plan !== clinic.plan ||
    seatLimit !== clinic.seat_limit ||
    icdVersion !== clinic.icd_version ||
    timezone !== clinic.timezone ||
    locationName !== primaryName

  return (
    <div className="space-y-5 p-8">
      <button
        onClick={() => navigate('/platform/clinics')}
        className="flex items-center gap-1.5 text-[13px] text-tx-3 hover:text-tx"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('platform.back_to_clinics')}
      </button>

      <PageHeader
        eyebrow={clinic.slug}
        title={clinic.legal_name}
        action={<Badge tone={STATUS_TONE[clinic.status]}>{t(`platform.status_${clinic.status}`)}</Badge>}
      />

      <Card>
        <CardHeader title={t('platform.clinic_info')} />
        <form
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
          className="space-y-4 p-5"
        >
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('platform.f_legal_name')} value={legalName} onChange={(e) => setLegalName(e.target.value)} required />
            <Input label={t('platform.f_tax_id')} value={taxId} onChange={(e) => setTaxId(e.target.value)} required />
            <Input label={t('platform.f_plan')} value={plan} onChange={(e) => setPlan(e.target.value)} />
            <Input
              label={t('platform.f_seat_limit')}
              type="number"
              min={1}
              value={seatLimit}
              onChange={(e) => setSeatLimit(Number(e.target.value))}
            />
            <Select label={t('platform.f_icd')} value={icdVersion} onChange={(e) => setIcdVersion(e.target.value)}>
              <option value="cie11">CIE-11</option>
              <option value="cie10">CIE-10</option>
            </Select>
            <Select label={t('platform.f_timezone')} value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              {TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value}>
                  {tz.label}
                </option>
              ))}
            </Select>
            <Input
              label={t('platform.f_location')}
              value={locationName}
              onChange={(e) => setLocationName(e.target.value)}
              required
            />
            <Input label={t('platform.f_slug')} value={clinic.slug} disabled />
          </div>
          <div className="flex justify-end">
            <Button type="submit" loading={save.isPending} disabled={!dirty || save.isPending}>
              {t('app.save')}
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <CardHeader title={t('platform.status_actions')} />
        <div className="flex flex-wrap gap-2 p-5">
          {clinic.status !== 'active' && (
            <Button variant="outline" loading={setStatus.isPending} onClick={() => setStatus.mutate('active')}>
              {t('platform.action_activate')}
            </Button>
          )}
          {clinic.status === 'active' && (
            <Button variant="outline" loading={setStatus.isPending} onClick={() => setStatus.mutate('suspended')}>
              {t('platform.action_suspend')}
            </Button>
          )}
          {clinic.status !== 'archived' && (
            <Button variant="danger" loading={setStatus.isPending} onClick={() => setStatus.mutate('archived')}>
              {t('platform.action_archive')}
            </Button>
          )}
          {clinic.status === 'active' && (
            <Button
              variant="subtle"
              loading={impersonate.isPending}
              onClick={() => {
                setSupportReason('')
                setSupportOpen(true)
              }}
            >
              <LogIn className="h-4 w-4" />
              {t('platform.action_impersonate')}
            </Button>
          )}
        </div>
      </Card>

      {stats && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard icon={Users} label={t('platform.total_patients')} value={String(stats.patients)} />
          <StatCard icon={Activity} label={t('platform.total_users')} value={String(stats.users)} />
          <StatCard icon={CalendarCheck} label={t('platform.total_appointments')} value={String(stats.appointments)} />
          <StatCard icon={FileText} label={t('platform.col_records')} value={String(stats.records)} />
        </div>
      )}

      <Card>
        <CardHeader title={t('platform.users_title')} />
        <div className="flex items-center justify-between gap-4 px-5 pb-2">
          <div className="relative w-80">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
            <input
              value={userQ}
              onChange={(e) => {
                setUserQ(e.target.value)
                setOffset(0)
              }}
              placeholder={t('platform.users_search_ph')}
              className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-3">
            <Select value={roleFilter} onChange={(e) => { setRoleFilter(e.target.value); setOffset(0) }}>
              <option value="all">{t('app.all')}</option>
              {(['admin', 'doctor', 'nurse', 'receptionist'] as const).map((r) => (
                <option key={r} value={r}>
                  {t(`role.${r}`)}
                </option>
              ))}
            </Select>
            <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setOffset(0) }}>
              <option value="all">{t('app.all')}</option>
              {(['active', 'suspended'] as const).map((s) => (
                <option key={s} value={s}>
                  {t(`status.${s}`)}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <Table>
          <thead>
            <Tr>
              <Th>{t('platform.col_name')}</Th>
              <Th>{t('login.email')}</Th>
              <Th>{t('users.col_role')}</Th>
              <Th>{t('platform.col_status')}</Th>
              <Th />
            </Tr>
          </thead>
          <tbody>
            {pagedUsers.map((u) => (
              <Tr key={u.id}>
                <Td className="font-medium text-tx">{u.name}</Td>
                <Td className="text-[13px]">{u.email}</Td>
                <Td>{t(`role.${u.role}`)}</Td>
                <Td>
                  <Badge tone={statusTone(u.status)}>{t(`status.${u.status}`)}</Badge>
                </Td>
                <Td className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditTarget(u)}>
                      <Pencil className="h-3.5 w-3.5" />
                      {t('app.edit')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={resetPassword.isPending && resetPassword.variables === u.id}
                      onClick={() => resetPassword.mutate(u.id)}
                    >
                      <KeyRound className="h-3.5 w-3.5" />
                      {t('platform.reset_password')}
                    </Button>
                    {u.status === 'active' ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-danger hover:bg-[var(--danger-10)]"
                        onClick={() => setDeactivateTarget(u)}
                      >
                        {t('users.deactivate')}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={reactivate.isPending && reactivate.variables === u.id}
                        onClick={() => reactivate.mutate(u.id)}
                      >
                        {t('users.activate')}
                      </Button>
                    )}
                  </div>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        {filteredUsers.length > PAGE_SIZE && (
          <Pager offset={offset} limit={PAGE_SIZE} count={pagedUsers.length} total={filteredUsers.length} onChange={setOffset} />
        )}
      </Card>

      {/* Roles & permissions */}
      <Card>
        <CardHeader title={t('permissions.title')} />
        {permMatrix && (
          <PermissionsMatrixTable
            matrix={permMatrix}
            busy={savePerms.isPending || resetPerms.isPending}
            onSaveRole={(role, permissions) => savePerms.mutate({ role, permissions })}
            onResetRole={(role) => resetPerms.mutate(role)}
          />
        )}
      </Card>

      <EditUserModal
        tenantId={id}
        user={editTarget}
        onClose={() => setEditTarget(null)}
        onDone={() => qc.invalidateQueries({ queryKey: ['platform-tenant-users', id] })}
      />

      <Modal open={supportOpen} onClose={() => setSupportOpen(false)} title={t('platform.support_reason_title')}>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            impersonate.mutate(supportReason.trim())
          }}
          className="space-y-4 p-5"
        >
          <div>
            <Input
              label={t('platform.support_reason_label')}
              value={supportReason}
              onChange={(e) => setSupportReason(e.target.value)}
              placeholder={t('platform.support_reason_ph')}
              required
            />
            <p className="mt-1.5 text-xs text-tx-3">{t('platform.support_reason_hint')}</p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setSupportOpen(false)}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" loading={impersonate.isPending} disabled={!supportReason.trim()}>
              <LogIn className="h-4 w-4" />
              {t('platform.action_impersonate')}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!deactivateTarget}
        onClose={() => setDeactivateTarget(null)}
        title={t('users.deactivate_title')}
      >
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('users.deactivate_confirm')}</p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeactivateTarget(null)}>
              {t('app.cancel')}
            </Button>
            <Button
              variant="danger"
              loading={suspend.isPending}
              onClick={() => deactivateTarget && suspend.mutate(deactivateTarget.id)}
            >
              {t('users.deactivate')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function EditUserModal({
  tenantId,
  user,
  onClose,
  onDone,
}: {
  tenantId: string
  user: User | null
  onClose: () => void
  onDone: () => void
}) {
  const t = useT()
  const [form, setForm] = useState({ name: '', role: 'nurse', sex: 'female', phone: '', specialty: '' })

  useEffect(() => {
    if (user)
      setForm({
        name: user.name,
        role: user.role,
        sex: user.sex ?? 'female',
        phone: user.phone ?? '',
        specialty: user.specialty ?? '',
      })
  }, [user])

  const update = useMutation({
    mutationFn: () =>
      platformTenantsApi.updateUser(tenantId, user!.id, {
        name: form.name,
        role: form.role,
        sex: form.sex || null,
        phone: form.phone || null,
        specialty: form.specialty || null,
      }),
    onSuccess: () => {
      toast(t('users.updated_ok'))
      onDone()
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={!!user} onClose={onClose} title={t('users.edit')}>
      {user && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            update.mutate()
          }}
          className="space-y-4 p-5"
        >
          <Input
            label={t('users.name')}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <div className="grid grid-cols-2 gap-4">
            <Select label={t('users.col_role')} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="doctor">{t('role.doctor')}</option>
              <option value="nurse">{t('role.nurse')}</option>
              <option value="receptionist">{t('role.receptionist')}</option>
              <option value="admin">{t('role.admin')}</option>
            </Select>
            <Select label={t('users.sex')} value={form.sex} onChange={(e) => setForm({ ...form, sex: e.target.value })}>
              <option value="female">{t('sex.female')}</option>
              <option value="male">{t('sex.male')}</option>
              <option value="other">{t('sex.other')}</option>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('users.phone')} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <Input
              label={t('users.col_specialty')}
              value={form.specialty}
              onChange={(e) => setForm({ ...form, specialty: e.target.value })}
            />
          </div>
          <Input label={t('login.email')} value={user.email} disabled />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" loading={update.isPending} disabled={!form.name}>
              {t('app.save')}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

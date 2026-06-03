import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ConciergeBell, HeartPulse, KeyRound, Pencil, Plus, Search, ShieldCheck, Stethoscope } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { usersApi } from '@/api/users'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { statusTone } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { fmtDateTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Role, User } from '@/types'

/** "miembro" / "miembros" depending on the count. */
function unitMembers(n: number, t: (k: string) => string): string {
  return n === 1 ? t('users.unit_member') : t('users.unit_members')
}

/** A readable temporary password the admin can hand off (user must change it on first login). */
function genPassword(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
  return Array.from({ length: 10 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

interface UserFieldsState {
  name: string
  role: string
  sex: string
  phone: string
  specialty: string
}

export function UsersPage() {
  const t = useT()
  const qc = useQueryClient()
  const [inviteOpen, setInviteOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<User | null>(null)
  const [resetTarget, setResetTarget] = useState<User | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null)
  const [roleFilter, setRoleFilter] = useState<'all' | Role>('all')
  const [q, setQ] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list({ limit: 200 }),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['users'] })

  const all = data?.items ?? []
  const countBy = (role: Role) => all.filter((u) => u.role === role).length
  const term = q.trim().toLowerCase()
  const visible = all.filter(
    (u) =>
      (roleFilter === 'all' || u.role === roleFilter) &&
      (!term || u.name.toLowerCase().includes(term) || u.email.toLowerCase().includes(term)),
  )

  const suspend = useMutation({
    mutationFn: (id: string) => usersApi.suspend(id),
    onSuccess: () => {
      invalidate()
      toast(t('users.deactivated_ok'))
      setDeactivateTarget(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const reactivate = useMutation({
    mutationFn: (id: string) => usersApi.reactivate(id),
    onSuccess: () => {
      invalidate()
      toast(t('users.activated_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={`${data?.total ?? 0} miembros`}
        title={t('users.title')}
        action={
          <Button onClick={() => setInviteOpen(true)}>
            <Plus className="h-4 w-4" />
            {t('users.invite')}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard icon={Stethoscope} label={t('users.stat_doctors')} value={String(countBy('doctor'))} unit={unitMembers(countBy('doctor'), t)} />
        <StatCard icon={HeartPulse} label={t('users.stat_nurses')} value={String(countBy('nurse'))} unit={unitMembers(countBy('nurse'), t)} />
        <StatCard icon={ConciergeBell} label={t('users.stat_reception')} value={String(countBy('receptionist'))} unit={unitMembers(countBy('receptionist'), t)} />
        <StatCard icon={ShieldCheck} label={t('users.stat_admin')} value={String(countBy('admin'))} unit={unitMembers(countBy('admin'), t)} />
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('users.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        <Segmented
          value={roleFilter}
          onChange={setRoleFilter}
          options={[
            { value: 'all', label: t('app.all') },
            { value: 'doctor', label: t('role.doctor') },
            { value: 'nurse', label: t('role.nurse') },
            { value: 'receptionist', label: t('role.receptionist') },
            { value: 'admin', label: t('role.admin') },
          ]}
        />
      </div>

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t('users.col_member')}</Th>
                <Th>{t('users.col_role')}</Th>
                <Th>{t('users.col_specialty')}</Th>
                <Th>{t('users.col_status')}</Th>
                <Th>{t('users.col_last_seen')}</Th>
                <Th>{t('users.col_actions')}</Th>
              </tr>
            </thead>
            <tbody>
              {visible.map((u) => (
                <Tr key={u.id}>
                  <Td>
                    <div className="flex items-center gap-3">
                      <Avatar name={u.name} size="sm" />
                      <div>
                        <p className="font-medium text-tx">{u.name}</p>
                        <p className="text-xs text-tx-3">{u.email}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>{t(`role.${u.role}`)}</Td>
                  <Td>{u.specialty ?? '—'}</Td>
                  <Td>
                    <Badge tone={statusTone(u.status)}>{t(`status.${u.status}`)}</Badge>
                  </Td>
                  <Td>{fmtDateTime(u.last_seen_at)}</Td>
                  <Td>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditTarget(u)}>
                        <Pencil className="h-3.5 w-3.5" />
                        {t('app.edit')}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setResetTarget(u)}>
                        <KeyRound className="h-3.5 w-3.5" />
                        {t('users.reset_password')}
                      </Button>
                      {u.status === 'active' ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-danger hover:bg-[var(--danger-10)]"
                          onClick={() => setDeactivateTarget(u)}
                        >
                          {t('users.deactivate')}
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
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
        )}
      </Card>

      <InviteModal open={inviteOpen} onClose={() => setInviteOpen(false)} onDone={invalidate} />
      <EditUserModal user={editTarget} onClose={() => setEditTarget(null)} onDone={invalidate} />
      <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />

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

/** Shared profile fields used by both the create and edit user forms. */
function UserFields({
  value,
  onChange,
}: {
  value: UserFieldsState
  onChange: (next: UserFieldsState) => void
}) {
  const t = useT()
  const set = (patch: Partial<UserFieldsState>) => onChange({ ...value, ...patch })
  return (
    <>
      <Input label={t('users.name')} value={value.name} onChange={(e) => set({ name: e.target.value })} required />
      <div className="grid grid-cols-2 gap-4">
        <Select label={t('users.col_role')} value={value.role} onChange={(e) => set({ role: e.target.value })}>
          <option value="doctor">{t('role.doctor')}</option>
          <option value="nurse">{t('role.nurse')}</option>
          <option value="receptionist">{t('role.receptionist')}</option>
          <option value="admin">{t('role.admin')}</option>
        </Select>
        <Select label={t('users.sex')} value={value.sex} onChange={(e) => set({ sex: e.target.value })}>
          <option value="female">{t('sex.female')}</option>
          <option value="male">{t('sex.male')}</option>
          <option value="other">{t('sex.other')}</option>
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Input label={t('users.phone')} value={value.phone} onChange={(e) => set({ phone: e.target.value })} />
        <Input
          label={t('users.col_specialty')}
          value={value.specialty}
          onChange={(e) => set({ specialty: e.target.value })}
        />
      </div>
    </>
  )
}

function InviteModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const t = useT()
  const empty = { name: '', email: '', role: 'nurse', sex: 'female', phone: '', specialty: '', password: '' }
  const [form, setForm] = useState(empty)

  const invite = useMutation({
    mutationFn: () =>
      usersApi.invite({
        name: form.name,
        email: form.email,
        role: form.role,
        password: form.password,
        sex: form.sex || null,
        phone: form.phone || null,
        specialty: form.specialty || null,
      }),
    onSuccess: () => {
      toast(t('users.created_ok'))
      onDone()
      onClose()
      setForm(empty)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('users.invite')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          invite.mutate()
        }}
        className="space-y-4 p-5"
      >
        <UserFields value={form} onChange={(v) => setForm({ ...form, ...v })} />
        <Input
          label={t('login.email')}
          type="email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          required
        />
        <div>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                label={t('users.temp_password')}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                minLength={8}
              />
            </div>
            <Button type="button" variant="outline" onClick={() => setForm({ ...form, password: genPassword() })}>
              {t('users.generate')}
            </Button>
          </div>
          <p className="mt-1.5 text-xs text-tx-3">{t('users.temp_password_hint')}</p>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={invite.isPending}>
            {t('users.invite')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function EditUserModal({
  user,
  onClose,
  onDone,
}: {
  user: User | null
  onClose: () => void
  onDone: () => void
}) {
  const t = useT()
  const [form, setForm] = useState<UserFieldsState | null>(null)

  useEffect(() => {
    setForm(
      user
        ? {
            name: user.name,
            role: user.role,
            sex: user.sex ?? 'female',
            phone: user.phone ?? '',
            specialty: user.specialty ?? '',
          }
        : null,
    )
  }, [user])

  const update = useMutation({
    mutationFn: () =>
      usersApi.update(user!.id, {
        name: form!.name,
        role: form!.role,
        sex: form!.sex || null,
        phone: form!.phone || null,
        specialty: form!.specialty || null,
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
      {form && user && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            update.mutate()
          }}
          className="space-y-4 p-5"
        >
          <UserFields value={form} onChange={setForm} />
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

function ResetPasswordModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const t = useT()
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (user) setPassword('')
  }, [user])

  const reset = useMutation({
    mutationFn: () => usersApi.resetPassword(user!.id, password),
    onSuccess: () => {
      toast(t('users.password_reset_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={!!user} onClose={onClose} title={t('users.reset_password_title')}>
      {user && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            reset.mutate()
          }}
          className="space-y-4 p-5"
        >
          <p className="text-sm text-tx-2">{user.name}</p>
          <div>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Input
                  label={t('users.new_temp_password')}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                />
              </div>
              <Button type="button" variant="outline" onClick={() => setPassword(genPassword())}>
                {t('users.generate')}
              </Button>
            </div>
            <p className="mt-1.5 text-xs text-tx-3">{t('users.temp_password_hint')}</p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" loading={reset.isPending}>
              {t('users.reset_password')}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

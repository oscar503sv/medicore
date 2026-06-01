import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { usersApi } from '@/api/users'
import { PageHeader } from '@/components/PageHeader'
import { Avatar } from '@/components/ui/Avatar'
import { Badge, statusTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { fmtDateTime } from '@/lib/format'
import { useT } from '@/lib/i18n'

export function UsersPage() {
  const t = useT()
  const qc = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={`${data?.total ?? 0} miembros`}
        title={t('users.title')}
        action={
          <Button onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            {t('users.invite')}
          </Button>
        }
      />

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
              </tr>
            </thead>
            <tbody>
              {data?.items.map((u) => (
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
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <InviteModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onInvited={() => qc.invalidateQueries({ queryKey: ['users'] })}
      />
    </div>
  )
}

function InviteModal({
  open,
  onClose,
  onInvited,
}: {
  open: boolean
  onClose: () => void
  onInvited: () => void
}) {
  const t = useT()
  const [form, setForm] = useState({ name: '', email: '', role: 'nurse', specialty: '' })

  const invite = useMutation({
    mutationFn: () =>
      usersApi.invite({ ...form, specialty: form.specialty || null }),
    onSuccess: () => {
      toast('Invitación enviada')
      onInvited()
      onClose()
      setForm({ name: '', email: '', role: 'nurse', specialty: '' })
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
        <Input label="Nombre" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <Input
          label={t('login.email')}
          type="email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          required
        />
        <div className="grid grid-cols-2 gap-4">
          <Select label={t('users.col_role')} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="doctor">{t('role.doctor')}</option>
            <option value="nurse">{t('role.nurse')}</option>
            <option value="receptionist">{t('role.receptionist')}</option>
            <option value="admin">{t('role.admin')}</option>
          </Select>
          <Input
            label={t('users.col_specialty')}
            value={form.specialty}
            onChange={(e) => setForm({ ...form, specialty: e.target.value })}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
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

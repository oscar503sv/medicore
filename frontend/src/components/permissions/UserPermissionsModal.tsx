import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Lock, RotateCcw } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { usersApi } from '@/api/users'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { DOCTOR_ONLY, GROUP_ICONS, groupByResource, isFixedFor, sameSet } from '@/lib/permissions'
import type { Permission, User, UserPermissions } from '@/types'

/** A user's permissions as their role's set plus exceptions. Saving the role's exact set
 * removes every exception, so later changes to the role reach the user again. */
export function UserPermissionsModal({
  user,
  onClose,
}: {
  user: User | null
  onClose: () => void
}) {
  const t = useT()
  const { data } = useQuery({
    queryKey: ['user-permissions', user?.id],
    queryFn: () => usersApi.permissions(user!.id),
    enabled: !!user,
  })

  return (
    <Modal
      open={!!user}
      onClose={onClose}
      title={user && `${t('uperm.title')} · ${user.name}`}
      width="max-w-2xl"
    >
      {data && data.user.id === user?.id ? (
        // Re-mounted after each save so the draft starts from the stored state.
        <PermissionsForm key={JSON.stringify(data)} data={data} onClose={onClose} />
      ) : (
        <PageLoader />
      )}
    </Modal>
  )
}

function wantedFrom(data: UserPermissions): Permission[] {
  return [...data.role_permissions.filter((p) => !data.revoked.includes(p)), ...data.granted]
}

function PermissionsForm({ data, onClose }: { data: UserPermissions; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const stored = useMemo(() => wantedFrom(data), [data])
  const [draft, setDraft] = useState<Permission[]>(stored)
  const groups = useMemo(() => groupByResource(data.catalog), [data.catalog])
  const isDoctor = data.user.role === 'doctor'
  const editable = data.available

  const save = useMutation({
    mutationFn: (permissions: Permission[]) =>
      usersApi.updatePermissions(data.user.id, permissions),
    onSuccess: (view) => {
      qc.setQueryData(['user-permissions', data.user.id], view)
      qc.invalidateQueries({ queryKey: ['users'] })
      toast(t('uperm.saved_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const toggle = (p: Permission) =>
    setDraft((d) => (d.includes(p) ? d.filter((x) => x !== p) : [...d, p]))

  const extra = draft.filter((p) => !data.role_permissions.includes(p)).length
  const removed = data.role_permissions.filter((p) => !draft.includes(p)).length
  const dirty = !sameSet(draft, stored)
  const atRole = sameSet(draft, data.role_permissions)

  return (
    <div className="flex max-h-[75vh] flex-col">
      <div className="space-y-2 border-b border-line px-5 py-4">
        <p className="text-[13px] text-tx-2">
          {t('uperm.desc').replace('{role}', t(`role.${data.user.role}`))}
        </p>
        {!editable && (
          <p className="rounded-md bg-[var(--warn-10)] px-3 py-2 text-[13px] text-warn">
            {t('uperm.not_in_plan')}
          </p>
        )}
        <div className="flex flex-wrap gap-1.5 text-xs">
          <Badge>
            {t('uperm.count')
              .replace('{n}', String(draft.length))
              .replace('{total}', String(data.catalog.length))}
          </Badge>
          {extra > 0 && (
            <Badge tone="accent">{t('uperm.extra_count').replace('{n}', String(extra))}</Badge>
          )}
          {removed > 0 && (
            <Badge tone="warn">{t('uperm.removed_count').replace('{n}', String(removed))}</Badge>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-3">
        {groups.map(([resource, permissions]) => {
          const GroupIcon = GROUP_ICONS[resource] ?? KeyRound
          return (
            <section key={resource} className="mb-3">
              <h4 className="mb-1 inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-tx-3">
                <GroupIcon className="h-3.5 w-3.5" />
                {t(`permgroup.${resource}`)}
              </h4>
              <ul>
                {permissions.map((p) => {
                  const doctorOnly = DOCTOR_ONLY.includes(p)
                  const fixed = isFixedFor(data.user.role, p)
                  const checked = fixed ? doctorOnly && isDoctor : draft.includes(p)
                  const inRole = data.role_permissions.includes(p)
                  const locked = data.locked.includes(p)
                  return (
                    <li key={p}>
                      <label
                        className={cn(
                          'flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-surface-2/60',
                          locked && 'opacity-60',
                          fixed || !editable ? 'cursor-default' : 'cursor-pointer',
                        )}
                        title={
                          !fixed
                            ? undefined
                            : doctorOnly
                              ? t('permissions.doctor_only')
                              : t('permissions.admin_only')
                        }
                      >
                        {fixed ? (
                          <Lock className="h-3.5 w-3.5 shrink-0 text-tx-4" />
                        ) : (
                          <Checkbox
                            checked={checked}
                            disabled={!editable || save.isPending}
                            onChange={() => toggle(p)}
                            aria-label={p}
                          />
                        )}
                        <span className="flex-1">
                          <span className="block text-[13px] text-tx">
                            {t(`permission.${p.replace('.', '_')}`)}
                          </span>
                          <span className="block text-[11px] text-tx-4">
                            {p}
                            {locked && (
                              <span className="ml-2 text-warn">
                                {t('sub.module_not_contracted')}
                              </span>
                            )}
                          </span>
                        </span>
                        {!fixed && checked && !inRole && (
                          <Badge tone="accent">{t('uperm.extra')}</Badge>
                        )}
                        {!fixed && !checked && inRole && (
                          <Badge tone="warn">{t('uperm.removed')}</Badge>
                        )}
                      </label>
                    </li>
                  )
                })}
              </ul>
            </section>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-5 py-3">
        <Button
          variant="ghost"
          disabled={!editable || atRole || save.isPending}
          onClick={() => setDraft([...data.role_permissions])}
        >
          <RotateCcw className="h-3.5 w-3.5" />
          {t('uperm.reset')}
        </Button>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('app.close')}
          </Button>
          <Button
            disabled={!editable || !dirty}
            loading={save.isPending}
            onClick={() => save.mutate(draft)}
          >
            {t('app.save')}
          </Button>
        </div>
      </div>
    </div>
  )
}

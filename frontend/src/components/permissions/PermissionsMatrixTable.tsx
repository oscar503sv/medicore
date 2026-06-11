import { Fragment, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Building2,
  CalendarDays,
  Check,
  Clock,
  FileText,
  KeyRound,
  Lock,
  Pill,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  Stethoscope,
  UserCog,
  Users,
} from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import type { Permission, PermissionsMatrix, Role } from '@/types'

// Column order: admin first (locked reference), then clinical roles.
const ROLES: Role[] = ['admin', 'doctor', 'nurse', 'receptionist']

// Clinical/legal guardrail mirrored from the backend: only doctors may hold these,
// and they cannot be taken away from them. Rendered locked in every column.
const DOCTOR_ONLY: Permission[] = ['records.sign', 'records.amend']

const GROUP_ICONS: Record<string, typeof Users> = {
  patients: Users,
  appointments: CalendarDays,
  availability: Clock,
  consultations: Stethoscope,
  records: FileText,
  prescriptions: Pill,
  diagnoses: Activity,
  insurers: ShieldCheck,
  users: UserCog,
  organization: Building2,
  audit: ScrollText,
  permissions: KeyRound,
}

interface Props {
  matrix: PermissionsMatrix
  onSaveRole: (role: Role, permissions: Permission[]) => void
  onResetRole: (role: Role) => void
  busy?: boolean
}

type Draft = Record<Role, Permission[]>

function draftFrom(matrix: PermissionsMatrix): Draft {
  return Object.fromEntries(
    ROLES.map((role) => [role, [...matrix.roles[role].effective]]),
  ) as Draft
}

function sameSet(a: Permission[], b: Permission[]) {
  return a.length === b.length && a.every((p) => b.includes(p))
}

export function PermissionsMatrixTable({ matrix, onSaveRole, onResetRole, busy }: Props) {
  const t = useT()
  const [draft, setDraft] = useState<Draft>(() => draftFrom(matrix))

  // Re-sync local edits whenever the server matrix changes (save/reset round-trips).
  useEffect(() => setDraft(draftFrom(matrix)), [matrix])

  const groups = useMemo(() => {
    const byResource = new Map<string, Permission[]>()
    for (const p of matrix.catalog) {
      const resource = p.split('.')[0]
      byResource.set(resource, [...(byResource.get(resource) ?? []), p])
    }
    return [...byResource.entries()]
  }, [matrix.catalog])

  const total = matrix.catalog.length

  const toggle = (role: Role, permission: Permission) => {
    setDraft((d) => {
      const current = d[role]
      const next = current.includes(permission)
        ? current.filter((p) => p !== permission)
        : [...current, permission]
      return { ...d, [role]: next }
    })
  }

  const isLocked = (role: Role, permission: Permission) =>
    role === 'admin' || DOCTOR_ONLY.includes(permission)

  return (
    <>
      <Table>
        <thead>
          <Tr>
            <Th className="align-top">{t('permissions.col_permission')}</Th>
            {ROLES.map((role) => {
              const dirty = !sameSet(draft[role], matrix.roles[role].effective)
              return (
                <Th key={role} className="border-l border-line-soft text-center align-top">
                  <div className="flex flex-col items-center gap-1.5 py-0.5">
                    <span className="inline-flex items-center gap-1.5">
                      {role === 'admin' && <Lock className="h-3 w-3" />}
                      {t(`role.${role}`)}
                      {matrix.roles[role].customized && (
                        <Badge tone="accent">{t('permissions.customized')}</Badge>
                      )}
                    </span>
                    <span className="font-mono text-[11px] normal-case tracking-normal text-tx-4">
                      {draft[role].length}/{total}
                    </span>
                    {role === 'admin' ? (
                      <span className="text-[10px] normal-case tracking-normal text-tx-4">
                        {t('permissions.admin_locked')}
                      </span>
                    ) : dirty ? (
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          disabled={busy}
                          onClick={() => onSaveRole(role, draft[role])}
                        >
                          {t('app.save')}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy}
                          onClick={() =>
                            setDraft((d) => ({
                              ...d,
                              [role]: [...matrix.roles[role].effective],
                            }))
                          }
                        >
                          {t('permissions.discard')}
                        </Button>
                      </div>
                    ) : matrix.roles[role].customized ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onResetRole(role)}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        {t('permissions.reset')}
                      </Button>
                    ) : null}
                  </div>
                </Th>
              )
            })}
          </Tr>
        </thead>
        <tbody>
          {groups.map(([resource, permissions]) => {
            const GroupIcon = GROUP_ICONS[resource] ?? KeyRound
            return (
              <Fragment key={resource}>
                <Tr>
                  <td
                    colSpan={ROLES.length + 1}
                    className="border-b border-line-soft bg-surface-2 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-tx-3"
                  >
                    <span className="inline-flex items-center gap-2">
                      <GroupIcon className="h-3.5 w-3.5" />
                      {t(`permgroup.${resource}`)}
                    </span>
                  </td>
                </Tr>
                {permissions.map((permission) => (
                  <Tr key={permission} className="transition-colors hover:bg-surface-2/60">
                    <Td>
                      <p className="text-[13px] text-tx">
                        {t(`permission.${permission.replace('.', '_')}`)}
                      </p>
                      <p className="text-[11px] text-tx-4">{permission}</p>
                    </Td>
                    {ROLES.map((role) => {
                      const locked = isLocked(role, permission)
                      const checked = draft[role].includes(permission)
                      const changed =
                        !locked &&
                        checked !== matrix.roles[role].effective.includes(permission)
                      return (
                        <td
                          key={role}
                          onClick={() => !locked && !busy && toggle(role, permission)}
                          title={
                            role === 'admin'
                              ? t('permissions.full_access')
                              : DOCTOR_ONLY.includes(permission)
                                ? t('permissions.doctor_only')
                                : undefined
                          }
                          className={cn(
                            'border-b border-l border-line-soft px-4 py-3 text-center',
                            !locked && !busy && 'cursor-pointer',
                          )}
                        >
                          {locked ? (
                            checked ? (
                              <Check className="mx-auto h-4 w-4 text-accent" />
                            ) : (
                              <Lock className="mx-auto h-3.5 w-3.5 text-tx-4" />
                            )
                          ) : (
                            <Checkbox
                              checked={checked}
                              disabled={busy}
                              onChange={() => toggle(role, permission)}
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`${role}: ${permission}`}
                              className={cn(changed && 'ring-2 ring-accent ring-offset-1')}
                            />
                          )}
                        </td>
                      )
                    })}
                  </Tr>
                ))}
              </Fragment>
            )
          })}
        </tbody>
      </Table>
      <p className="border-t border-line px-5 py-3 text-[12px] text-tx-3">
        {t('permissions.actions_hint')}
      </p>
    </>
  )
}

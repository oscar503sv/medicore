import { Fragment, useEffect, useMemo, useState } from 'react'
import { Lock, RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { useT } from '@/lib/i18n'
import type { Permission, PermissionsMatrix, Role } from '@/types'

// Column order: admin first (locked reference), then clinical roles.
const ROLES: Role[] = ['admin', 'doctor', 'nurse', 'receptionist']

// Clinical/legal guardrail mirrored from the backend: only doctors may hold these,
// and they cannot be taken away from them. Rendered locked in every column.
const DOCTOR_ONLY: Permission[] = ['records.sign', 'records.amend']

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
    <Table>
      <thead>
        <Tr>
          <Th>{t('permissions.col_permission')}</Th>
          {ROLES.map((role) => (
            <Th key={role} className="text-center">
              <span className="inline-flex items-center gap-1.5">
                {role === 'admin' && <Lock className="h-3 w-3" />}
                {t(`role.${role}`)}
                {matrix.roles[role].customized && (
                  <Badge tone="accent">{t('permissions.customized')}</Badge>
                )}
              </span>
            </Th>
          ))}
        </Tr>
      </thead>
      <tbody>
        {groups.map(([resource, permissions]) => (
          <Fragment key={resource}>
            <Tr>
              <td
                colSpan={ROLES.length + 1}
                className="border-b border-line-soft bg-surface-2 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-tx-3"
              >
                {t(`permgroup.${resource}`)}
              </td>
            </Tr>
            {permissions.map((permission) => (
              <Tr key={permission}>
                <Td>
                  <p className="text-[13px] text-tx">
                    {t(`permission.${permission.replace('.', '_')}`)}
                  </p>
                  <p className="text-[11px] text-tx-4">{permission}</p>
                </Td>
                {ROLES.map((role) => (
                  <Td key={role} className="text-center">
                    <Checkbox
                      checked={draft[role].includes(permission)}
                      disabled={busy || isLocked(role, permission)}
                      onChange={() => toggle(role, permission)}
                      aria-label={`${role}: ${permission}`}
                    />
                  </Td>
                ))}
              </Tr>
            ))}
          </Fragment>
        ))}
        <Tr>
          <Td className="text-[12px] text-tx-3">{t('permissions.actions_hint')}</Td>
          {ROLES.map((role) => {
            const dirty = !sameSet(draft[role], matrix.roles[role].effective)
            return (
              <Td key={role} className="text-center align-top">
                {role === 'admin' ? (
                  <span className="text-[11px] text-tx-4">{t('permissions.admin_locked')}</span>
                ) : (
                  <div className="flex flex-col items-center gap-1.5">
                    <Button
                      size="sm"
                      disabled={!dirty || busy}
                      onClick={() => onSaveRole(role, draft[role])}
                    >
                      {t('app.save')}
                    </Button>
                    {matrix.roles[role].customized && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onResetRole(role)}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        {t('permissions.reset')}
                      </Button>
                    )}
                  </div>
                )}
              </Td>
            )
          })}
        </Tr>
      </tbody>
    </Table>
  )
}

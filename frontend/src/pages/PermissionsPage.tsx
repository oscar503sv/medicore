import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '@/components/PageHeader'
import { PermissionsMatrixTable } from '@/components/permissions/PermissionsMatrixTable'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { errorMessage } from '@/api/client'
import { permissionsApi } from '@/api/permissions'
import { useT } from '@/lib/i18n'
import type { Permission, PermissionsMatrix, Role } from '@/types'

export function PermissionsPage() {
  const t = useT()
  const qc = useQueryClient()

  const { data: matrix, isLoading } = useQuery({
    queryKey: ['permissions-matrix'],
    queryFn: permissionsApi.getMatrix,
  })

  const refresh = (next: PermissionsMatrix) => {
    qc.setQueryData(['permissions-matrix'], next)
    toast(t('permissions.saved'))
  }

  const save = useMutation({
    mutationFn: ({ role, permissions }: { role: Role; permissions: Permission[] }) =>
      permissionsApi.updateRole(role, permissions),
    onSuccess: refresh,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const reset = useMutation({
    mutationFn: (role: Role) => permissionsApi.resetRole(role),
    onSuccess: refresh,
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !matrix) return <PageLoader />

  return (
    <div className="space-y-4">
      <PageHeader eyebrow={t('permissions.subtitle')} title={t('permissions.title')} />
      <Card>
        <PermissionsMatrixTable
          matrix={matrix}
          busy={save.isPending || reset.isPending}
          onSaveRole={(role, permissions) => save.mutate({ role, permissions })}
          onResetRole={(role) => reset.mutate(role)}
        />
      </Card>
    </div>
  )
}

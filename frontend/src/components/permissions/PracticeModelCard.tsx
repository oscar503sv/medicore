import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { permissionsApi } from '@/api/permissions'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import type { PermissionsMatrix, PracticeModel } from '@/types'

const MODELS: PracticeModel[] = ['associated', 'employed']

/** "How does your clinic work?": associated doctors (each sets prices and sees their own
 * income) or employed doctors (the administration sets prices and sees the money). It moves
 * the default permissions; roles and people can still be adjusted afterwards. */
export function PracticeModelCard({
  current,
  onSaved,
}: {
  current: PracticeModel
  onSaved: (matrix: PermissionsMatrix) => void
}) {
  const t = useT()
  const [pending, setPending] = useState<PracticeModel | null>(null)
  const save = useMutation({
    mutationFn: (model: PracticeModel) => permissionsApi.setPracticeModel(model),
    onSuccess: (matrix) => {
      setPending(null)
      onSaved(matrix)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Card>
      <CardHeader title={t('pm.title')} />
      <div className="space-y-4 p-5">
        <p className="text-[13px] text-tx-3">{t('pm.desc')}</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {MODELS.map((m) => {
            const active = m === current
            return (
              <div
                key={m}
                className={cn(
                  'flex flex-col justify-between gap-3 rounded-lg border p-4',
                  active ? 'border-accent bg-surface-2' : 'border-line',
                )}
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-tx">{t(`pm.${m}`)}</p>
                    {active && (
                      <Badge tone="accent">
                        <Check className="mr-1 inline h-3 w-3" />
                        {t('pm.current')}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 text-[13px] text-tx-3">{t(`pm.${m}_desc`)}</p>
                </div>
                {!active && (
                  <div>
                    <Button size="sm" variant="outline" onClick={() => setPending(m)}>
                      {t('pm.apply')}
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {pending && (
        <Modal open onClose={() => setPending(null)} title={t('pm.confirm_title')} width="max-w-md">
          <div className="space-y-4 p-5">
            <p className="text-sm text-tx-2">{t('pm.confirm')}</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setPending(null)}>
                {t('app.cancel')}
              </Button>
              <Button loading={save.isPending} onClick={() => save.mutate(pending)}>
                {t(`pm.${pending}`)}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </Card>
  )
}

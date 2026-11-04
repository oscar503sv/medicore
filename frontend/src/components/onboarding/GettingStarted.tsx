import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, Sparkles } from 'lucide-react'
import { authApi, type Onboarding, type OnboardingStep } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { greetingName } from '@/lib/user'
import { useAuthStore } from '@/stores/auth'

/** Where each step is done. */
const LINKS: Record<string, string> = {
  availability: '/availability',
  patient: '/patients',
  appointment: '/appointments',
  consultation: '/appointments',
  profile: '/settings',
  clinic: '/settings?section=organization',
  insurers: '/insurers',
  team: '/users',
  catalog: '/procedures/catalog',
  roles: '/permissions',
}

/**
 * First-login onboarding for doctors and admins: a one-time welcome modal and a
 * "getting started" checklist whose steps tick themselves off from real clinic data.
 * Renders nothing for other roles and once the user dismisses it.
 */
export function GettingStarted() {
  const t = useT()
  const qc = useQueryClient()
  const session = useAuthStore((s) => s.session)
  // Always fresh: steps tick off from work done on other pages.
  const { data } = useQuery({
    queryKey: ['onboarding'],
    queryFn: authApi.onboarding,
    staleTime: 0,
  })

  const update = useMutation({
    mutationFn: authApi.updateOnboarding,
    onMutate: (patch) =>
      qc.setQueryData<Onboarding>(
        ['onboarding'],
        (o) => o && { ...o, ...patch, steps: patch.dismissed ? [] : o.steps },
      ),
    onError: (err) => {
      qc.invalidateQueries({ queryKey: ['onboarding'] })
      toast(errorMessage(err), 'danger')
    },
  })

  if (!data || data.dismissed || data.steps.length === 0) return null

  const required = data.steps.filter((s) => !s.optional)
  const done = required.filter((s) => s.done).length
  const allDone = done === required.length
  const pct = Math.round((done / required.length) * 100)
  const who = greetingName(session?.name ?? '', session?.role, session?.sex)

  return (
    <>
      <Modal
        open={!data.welcome_seen}
        onClose={() => update.mutate({ welcome_seen: true })}
        title={t('ob.welcome_title')}
        width="max-w-lg"
      >
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">
            <span className="font-medium text-tx">
              {t('ob.welcome_hello').replace('{name}', who)}
            </span>{' '}
            {t(session?.role === 'admin' ? 'ob.welcome_admin' : 'ob.welcome_doctor')}
          </p>
          <ol className="space-y-2">
            {data.steps.map((s, i) => (
              <li key={s.key} className="flex items-center gap-3 text-sm text-tx">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-2 font-mono text-xs text-tx-2">
                  {i + 1}
                </span>
                {t(`ob.step.${s.key}`)}
                {s.optional && <Badge tone="neutral">{t('ob.optional')}</Badge>}
              </li>
            ))}
          </ol>
          <div className="flex justify-end">
            <Button onClick={() => update.mutate({ welcome_seen: true })}>
              <Sparkles className="h-4 w-4" />
              {t('ob.welcome_start')}
            </Button>
          </div>
        </div>
      </Modal>

      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent" />
              {t('ob.title')}
            </span>
          }
          action={
            <Button size="sm" variant="ghost" onClick={() => update.mutate({ dismissed: true })}>
              {t('ob.dismiss')}
            </Button>
          }
        />
        <div className="px-5 pt-4">
          <div className="flex items-center justify-between text-xs text-tx-3">
            <span>
              {allDone
                ? t('ob.all_done')
                : t('ob.progress')
                    .replace('{done}', String(done))
                    .replace('{total}', String(required.length))}
            </span>
            <span className="font-mono">{pct}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        <ul className="divide-y divide-line-soft px-1 pb-1 pt-2">
          {data.steps.map((s) => (
            <StepRow key={s.key} step={s} />
          ))}
        </ul>
      </Card>
    </>
  )
}

function StepRow({ step }: { step: OnboardingStep }) {
  const t = useT()
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <span
        className={cn(
          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border',
          step.done ? 'border-transparent bg-accent text-white' : 'border-line text-transparent',
        )}
      >
        <Check className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'flex items-center gap-2 text-sm font-medium',
            step.done ? 'text-tx-3 line-through' : 'text-tx',
          )}
        >
          {t(`ob.step.${step.key}`)}
          {step.optional && !step.done && <Badge tone="neutral">{t('ob.optional')}</Badge>}
        </p>
        {!step.done && <p className="text-xs text-tx-3">{t(`ob.step.${step.key}.desc`)}</p>}
      </div>
      {step.done ? (
        <span className="text-xs text-tx-3">{t('ob.done')}</span>
      ) : (
        <Link
          to={LINKS[step.key] ?? '/'}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-[13px] text-tx hover:bg-surface-2"
        >
          {t('ob.go')}
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </li>
  )
}

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { platformAuthApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { MfaEnrollment } from '@/components/platform/MfaEnrollment'
import { MfaManagement } from '@/components/platform/MfaManagement'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { useT } from '@/lib/i18n'

const PROFILE_KEY = ['platform-me']

export function PlatformSecurityPage() {
  const t = useT()
  const queryClient = useQueryClient()
  const [isEnrolling, setIsEnrolling] = useState(false)
  const {
    data: profile,
    isError,
    refetch,
  } = useQuery({
    queryKey: PROFILE_KEY,
    queryFn: platformAuthApi.me,
  })

  function handleChanged() {
    setIsEnrolling(false)
    void queryClient.invalidateQueries({ queryKey: PROFILE_KEY })
  }

  if (isError) {
    return (
      <div className="space-y-3 p-8">
        <p role="alert" className="text-sm text-danger">
          {t('sec.load_error')}
        </p>
        <Button variant="outline" onClick={() => void refetch()}>
          {t('sec.retry')}
        </Button>
      </div>
    )
  }
  if (!profile) return <PageLoader />

  // The enrollment flow stays on screen until its codes are saved, even though the profile
  // already reports MFA on by then.
  const isOn = profile.mfa_enabled && !isEnrolling

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('sec.title')} />
      <p className="-mt-2 text-[13px] text-tx-3">{t('sec.subtitle')}</p>

      <Card>
        <CardHeader
          title={t('sec.mfa_title')}
          action={
            <Badge tone={isOn ? 'ok' : 'neutral'}>
              {isOn ? t('sec.status_on') : t('sec.status_off')}
            </Badge>
          }
        />
        <div className="space-y-4 px-5 py-5">
          {!isEnrolling && <p className="max-w-xl text-[13px] text-tx-3">{t('sec.mfa_desc')}</p>}

          {isEnrolling ? (
            <MfaEnrollment
              account={profile.email}
              onCancel={() => setIsEnrolling(false)}
              onDone={handleChanged}
            />
          ) : profile.mfa_enabled ? (
            <MfaManagement
              account={profile.email}
              recoveryCodesRemaining={profile.recovery_codes_remaining}
              onChanged={handleChanged}
            />
          ) : (
            <Button onClick={() => setIsEnrolling(true)}>{t('sec.enable')}</Button>
          )}
        </div>
      </Card>
    </div>
  )
}

import { useState } from 'react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { platformAuthApi } from '@/api/platform'
import { errorCode, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { useT } from '@/lib/i18n'
import type { PlatformLoginResult } from '@/types'

const fieldLabel = 'mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-tx-3'
const fieldInput =
  'h-11 w-full rounded-[10px] border border-line bg-bg px-3 font-mono text-sm text-tx placeholder:text-tx-4 transition-colors focus:border-accent focus:outline-none'

interface PlatformMfaStepProps {
  onVerified: (result: PlatformLoginResult) => void
  /** Shows a message in the page's alert area ('' clears it). */
  onError: (message: string) => void
  /** Back to the password step; also used when the server says the challenge expired. */
  onBack: () => void
}

/** Second sign-in step: a 6-digit code from the authenticator app, or a recovery code. */
export function PlatformMfaStep({ onVerified, onError, onBack }: PlatformMfaStepProps) {
  const t = useT()
  const [isRecovery, setIsRecovery] = useState(false)
  const [code, setCode] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onError('')
    setIsLoading(true)
    try {
      onVerified(await platformAuthApi.verifyMfa(code.trim()))
    } catch (err) {
      // Back first: the page clears its alert when returning, and the message must survive.
      if (errorCode(err) === 'auth.mfa_challenge_expired') onBack()
      else setCode('')
      onError(errorMessage(err, t('platform.mfa.bad_code')))
    } finally {
      setIsLoading(false)
    }
  }

  function handleToggleRecovery() {
    setIsRecovery((v) => !v)
    setCode('')
    onError('')
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6 space-y-4">
      <div>
        <label htmlFor="platform-mfa-code" className={fieldLabel}>
          {isRecovery ? t('platform.mfa.recovery_label') : t('platform.mfa.code_label')}
        </label>
        {isRecovery ? (
          <input
            key="recovery"
            id="platform-mfa-code"
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={16}
            placeholder="xxxxx-xxxxx"
            aria-describedby="platform-mfa-hint"
            autoFocus
            required
            className={fieldInput}
          />
        ) : (
          <input
            key="totp"
            id="platform-mfa-code"
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            autoComplete="one-time-code"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="000000"
            aria-describedby="platform-mfa-hint"
            autoFocus
            required
            className={`${fieldInput} tracking-[0.4em]`}
          />
        )}
        <p id="platform-mfa-hint" className="mt-1.5 text-xs text-tx-3">
          {isRecovery ? t('platform.mfa.recovery_hint') : t('platform.mfa.code_hint')}
        </p>
      </div>

      <Button type="submit" size="lg" loading={isLoading} className="w-full">
        {t('platform.mfa.verify')}
        <ArrowRight className="h-4 w-4" />
      </Button>

      <div className="flex items-center justify-between text-[13px]">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1 text-tx-3 hover:text-tx"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('platform.mfa.back')}
        </button>
        <button
          type="button"
          onClick={handleToggleRecovery}
          className="text-accent hover:underline"
        >
          {isRecovery ? t('platform.mfa.use_app') : t('platform.mfa.use_recovery')}
        </button>
      </div>
    </form>
  )
}

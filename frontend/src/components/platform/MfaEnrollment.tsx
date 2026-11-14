import { useState } from 'react'
import { Copy, ExternalLink } from 'lucide-react'
import { platformAuthApi } from '@/api/platform'
import { errorMessage } from '@/api/client'
import { RecoveryCodesPanel } from '@/components/platform/RecoveryCodesPanel'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { groupSecret } from '@/lib/security'
import type { MfaSetup } from '@/types'

type Step = 'password' | 'key' | 'codes'

interface MfaEnrollmentProps {
  account: string
  onCancel: () => void
  /** Called once the recovery codes were saved and acknowledged. */
  onDone: () => void
}

/**
 * Turn two-step verification on: password, then the key and a first code, then the recovery
 * codes. The secret and the codes only live in this component's state, never in a query cache.
 */
export function MfaEnrollment({ account, onCancel, onDone }: MfaEnrollmentProps) {
  const t = useT()
  const [step, setStep] = useState<Step>('password')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [codes, setCodes] = useState<string[]>([])
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function run(action: () => Promise<void>) {
    setError('')
    setIsSubmitting(true)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleStart(e: React.FormEvent) {
    e.preventDefault()
    void run(async () => {
      setSetup(await platformAuthApi.mfaSetup(password))
      setPassword('')
      setStep('key')
    })
  }

  function handleConfirm(e: React.FormEvent) {
    e.preventDefault()
    void run(async () => {
      setCodes(await platformAuthApi.mfaConfirm(code))
      setSetup(null)
      setCode('')
      setStep('codes')
    })
  }

  function handleCopyKey() {
    if (!setup) return
    void navigator.clipboard?.writeText(setup.secret).then(() => toast(t('sec.key_copied')))
  }

  const errorAlert = error && (
    <p role="alert" className="text-[13px] text-danger">
      {error}
    </p>
  )

  if (step === 'codes') {
    return <RecoveryCodesPanel codes={codes} account={account} onDone={onDone} />
  }

  if (step === 'password' || !setup) {
    return (
      <form onSubmit={handleStart} className="max-w-sm space-y-3">
        <Input
          label={t('sec.password')}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          required
        />
        <p className="text-xs text-tx-3">{t('sec.password_hint')}</p>
        {errorAlert}
        <div className="flex gap-2">
          <Button type="submit" loading={isSubmitting}>
            {t('sec.continue')}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t('sec.cancel')}
          </Button>
        </div>
      </form>
    )
  }

  return (
    <div className="max-w-md space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-tx">{t('sec.step_key_title')}</h3>
        <p className="mt-1 text-[13px] text-tx-3">{t('sec.step_key_desc')}</p>
      </div>

      <div>
        <p className="mb-1.5 text-[13px] font-medium text-tx-2">{t('sec.key_label')}</p>
        <p className="rounded-lg border border-line bg-bg px-4 py-3 font-mono text-base tracking-wider text-tx">
          {groupSecret(setup.secret)}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
          <Button type="button" variant="outline" size="sm" onClick={handleCopyKey}>
            <Copy className="h-3.5 w-3.5" />
            {t('sec.copy_key')}
          </Button>
          <a
            href={setup.otpauth_uri}
            className="inline-flex items-center gap-1 text-[13px] text-accent hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {t('sec.open_in_app')}
          </a>
        </div>
        <p className="mt-1.5 text-xs text-tx-3">{t('sec.open_in_app_hint')}</p>
      </div>

      <form onSubmit={handleConfirm} className="space-y-3">
        <Input
          label={t('sec.confirm_code')}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          autoComplete="one-time-code"
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          placeholder="000000"
          className="font-mono"
          autoFocus
          required
        />
        {errorAlert}
        <div className="flex gap-2">
          <Button type="submit" loading={isSubmitting}>
            {t('sec.confirm')}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t('sec.cancel')}
          </Button>
        </div>
      </form>
    </div>
  )
}

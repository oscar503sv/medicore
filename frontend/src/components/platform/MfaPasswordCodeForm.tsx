import { useState } from 'react'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useT } from '@/lib/i18n'

interface MfaPasswordCodeFormProps {
  submitLabel: string
  isDanger?: boolean
  description?: string
  onSubmit: (password: string, code: string) => Promise<void>
  onCancel: () => void
}

/** Current password + authenticator code, asked before a sensitive MFA change. */
export function MfaPasswordCodeForm({
  submitLabel,
  isDanger = false,
  description,
  onSubmit,
  onCancel,
}: MfaPasswordCodeFormProps) {
  const t = useT()
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      await onSubmit(password, code)
    } catch (err) {
      setError(errorMessage(err))
      setCode('')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-sm space-y-3">
      {description && <p className="text-[13px] text-tx-3">{description}</p>}
      <Input
        label={t('sec.password')}
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />
      <Input
        label={t('sec.code')}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
        autoComplete="one-time-code"
        inputMode="numeric"
        pattern="[0-9]{6}"
        maxLength={6}
        placeholder="000000"
        className="font-mono"
        required
      />
      {error && (
        <p role="alert" className="text-[13px] text-danger">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" variant={isDanger ? 'danger' : 'accent'} loading={isSubmitting}>
          {submitLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t('sec.cancel')}
        </Button>
      </div>
    </form>
  )
}

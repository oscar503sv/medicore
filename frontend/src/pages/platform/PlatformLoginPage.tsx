import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { platformAuthApi } from '@/api/platform'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useT } from '@/lib/i18n'
import { usePlatformAuthStore } from '@/stores/platformAuth'

export function PlatformLoginPage() {
  const t = useT()
  const navigate = useNavigate()
  const setSession = usePlatformAuthStore((s) => s.setSession)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const session = await platformAuthApi.login(email.trim(), password)
      setSession(session)
      navigate('/platform/clinics')
    } catch (err) {
      setError(errorMessage(err, t('platform.bad_credentials')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <form onSubmit={handleSubmit} className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent">
            <ShieldAlert className="h-5 w-5 text-white" />
          </span>
          <span className="font-serif text-2xl text-tx">{t('platform.console')}</span>
        </div>

        <h1 className="font-serif text-3xl text-tx">{t('platform.login_title')}</h1>
        <p className="mt-1.5 text-sm text-tx-3">{t('platform.login_subtitle')}</p>

        {error && (
          <div className="mt-4 rounded-lg bg-[var(--danger-10)] px-3 py-2 text-[13px] text-danger">
            {error}
          </div>
        )}

        <div className="mt-6 space-y-4">
          <Input
            label={t('login.email')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="super@medicore.health"
            autoFocus
            required
          />
          <Input
            label={t('login.password')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
          <Button type="submit" size="lg" loading={loading} className="w-full">
            {t('login.submit')}
          </Button>
        </div>
      </form>
    </div>
  )
}

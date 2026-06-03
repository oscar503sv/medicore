import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Building2, Eye, EyeOff } from 'lucide-react'
import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { AuthBrand, AuthCard, AuthShell, ComplianceRow } from '@/components/AuthShell'
import { Button } from '@/components/ui/Button'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

const fieldLabel = 'mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-tx-3'
const fieldInput =
  'h-11 w-full rounded-[10px] border border-line bg-bg px-3 text-sm text-tx placeholder:text-tx-4 transition-colors focus:border-accent focus:outline-none'

export function LoginPage() {
  const t = useT()
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)

  const [slug, setSlug] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const session = await authApi.login({ slug: slug.trim(), email, password })
      setSession(session)
      navigate('/')
    } catch (err) {
      setError(errorMessage(err, 'Credenciales inválidas'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell>
      <AuthCard>
        <AuthBrand badge={t('login.badge')} />

        <div className="mt-6 text-center">
          <h1 className="font-serif text-[38px] leading-none text-tx">{t('login.title')}</h1>
          <p className="mt-2 text-sm text-tx-3">{t('login.subtitle')}</p>
        </div>

        {error && (
          <div className="mt-5 rounded-lg bg-[var(--danger-10)] px-3 py-2 text-[13px] text-danger">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="login-org" className={fieldLabel}>
              {t('login.org')}
            </label>
            <div className="relative flex items-center">
              <Building2 className="pointer-events-none absolute left-3 h-4 w-4 text-tx-3" />
              <input
                id="login-org"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="sanrafael"
                autoFocus
                required
                className={`${fieldInput} pl-9 font-mono`}
              />
            </div>
          </div>

          <div>
            <label htmlFor="login-email" className={fieldLabel}>
              {t('login.email')}
            </label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="elena.vasquez@medicore.health"
              required
              className={fieldInput}
            />
          </div>

          <div>
            <label htmlFor="login-password" className={fieldLabel}>
              {t('login.password')}
            </label>
            <div className="relative flex items-center">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className={`${fieldInput} pr-10`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                className="absolute right-2 rounded-md p-1.5 text-tx-3 transition-colors hover:text-tx"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <label className="flex items-center gap-2 whitespace-nowrap text-[13px] text-tx-2">
            <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-line accent-accent" />
            {t('login.remember')}
          </label>

          <Button type="submit" size="lg" loading={loading} className="w-full">
            {t('login.submit')}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </form>

        <ComplianceRow />
      </AuthCard>
    </AuthShell>
  )
}

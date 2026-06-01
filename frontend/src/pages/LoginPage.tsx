import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Monitor, Moon, ShieldCheck, Sun } from 'lucide-react'
import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUIStore, type Theme } from '@/stores/ui'

export function LoginPage() {
  const t = useT()
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)
  const { theme, setTheme, lang, setLang } = useUIStore()

  const [slug, setSlug] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const themeIcons: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Monitor }
  const ThemeIcon = themeIcons[theme]
  const cycleTheme = () => {
    const order: Theme[] = ['light', 'dark', 'system']
    setTheme(order[(order.indexOf(theme) + 1) % order.length])
  }

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
    <div className="flex min-h-screen">
      {/* Left editorial panel */}
      <div className="relative hidden flex-1 flex-col justify-between overflow-hidden bg-surface p-12 lg:flex">
        <div
          className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-pill opacity-30 blur-3xl"
          style={{ background: 'radial-gradient(circle, var(--accent) 0%, transparent 70%)' }}
        />
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent font-serif text-xl text-white">
            M
          </span>
          <span className="font-serif text-2xl text-tx">Medicore</span>
        </div>

        <div className="max-w-lg">
          <p className="font-serif text-4xl leading-tight text-tx">
            <span className="italic">{t('login.quote')}</span>
          </p>
          <p className="mt-4 text-sm text-tx-3">— William Osler</p>
        </div>

        <div className="flex gap-8">
          <div>
            <p className="font-serif text-3xl text-tx">99.9%</p>
            <p className="text-[13px] text-tx-3">Uptime</p>
          </div>
          <div>
            <p className="font-serif text-3xl text-tx">HIPAA</p>
            <p className="text-[13px] text-tx-3">Compliant</p>
          </div>
          <div>
            <p className="font-serif text-3xl text-tx">24/7</p>
            <p className="text-[13px] text-tx-3">Soporte</p>
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex w-full flex-col items-center justify-center bg-bg p-6 lg:w-[520px]">
        <div className="absolute right-6 top-6 flex gap-1">
          <button
            onClick={() => setLang(lang === 'es' ? 'en' : 'es')}
            className="rounded-md px-2.5 py-1.5 text-[13px] font-medium text-tx-2 hover:bg-surface-2"
          >
            {lang.toUpperCase()}
          </button>
          <button onClick={cycleTheme} className="rounded-md p-2 text-tx-2 hover:bg-surface-2">
            <ThemeIcon className="h-[18px] w-[18px]" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="w-full max-w-sm">
          <h1 className="font-serif text-3xl text-tx">{t('login.title')}</h1>
          <p className="mt-1.5 text-sm text-tx-3">{t('login.subtitle')}</p>

          {error && (
            <div className="mt-4 rounded-lg bg-[var(--danger-10)] px-3 py-2 text-[13px] text-danger">
              {error}
            </div>
          )}

          <div className="mt-6 space-y-4">
            <Input
              label={t('login.org')}
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="clinica-demo"
              autoFocus
              required
            />
            <Input
              label={t('login.email')}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="doctor@clinica.health"
              required
            />
            <div>
              <Input
                label={t('login.password')}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
              <button type="button" className="mt-1.5 text-[13px] text-accent hover:underline">
                {t('login.forgot')}
              </button>
            </div>

            <label className="flex items-center gap-2 text-[13px] text-tx-2">
              <input type="checkbox" className="rounded border-line accent-accent" />
              {t('login.remember')}
            </label>

            <Button type="submit" size="lg" loading={loading} className="w-full">
              {t('login.submit')}
            </Button>
          </div>

          <div className="mt-6 flex items-center justify-center gap-2 text-xs text-tx-4">
            <ShieldCheck className="h-3.5 w-3.5" />
            {t('login.encryption')}
          </div>
        </form>
      </div>
    </div>
  )
}

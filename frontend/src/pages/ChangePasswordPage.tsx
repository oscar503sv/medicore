import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

/** Password field with a show/hide toggle (mirrors the login screen). */
function PasswordField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{label}</span>
      <div className="relative flex items-center">
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required
          minLength={8}
          className="h-10 w-full rounded-lg border border-line bg-bg px-3 pr-10 text-sm text-tx placeholder:text-tx-4 transition-colors focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          className="absolute right-2 rounded-md p-1.5 text-tx-3 hover:text-tx"
          aria-label={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

export function ChangePasswordPage() {
  const t = useT()
  const navigate = useNavigate()
  const clearFlag = useAuthStore((s) => s.clearMustChangePassword)

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (next.length < 8) return setError(t('pwd.min'))
    if (next !== confirm) return setError(t('pwd.mismatch'))
    setLoading(true)
    try {
      await authApi.changePassword(current, next)
      clearFlag()
      toast(t('pwd.changed_ok'))
      navigate('/')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <form onSubmit={handleSubmit} className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent">
            <ShieldCheck className="h-5 w-5 text-white" />
          </span>
          <span className="font-serif text-2xl text-tx">Medicore</span>
        </div>

        <h1 className="font-serif text-3xl text-tx">{t('pwd.title')}</h1>
        <p className="mt-1.5 text-sm text-tx-3">{t('pwd.subtitle')}</p>

        {error && (
          <div className="mt-4 rounded-lg bg-[var(--danger-10)] px-3 py-2 text-[13px] text-danger">
            {error}
          </div>
        )}

        <div className="mt-6 space-y-4">
          <Input
            label={t('pwd.current')}
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            autoFocus
          />
          <PasswordField label={t('pwd.new')} value={next} onChange={setNext} />
          <PasswordField label={t('pwd.confirm')} value={confirm} onChange={setConfirm} />
          <Button type="submit" size="lg" loading={loading} className="w-full">
            {t('pwd.submit')}
          </Button>
        </div>
      </form>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Monitor, Moon, Smartphone, Sun } from 'lucide-react'
import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { PageHeader } from '@/components/PageHeader'
import { OrganizationSection } from '@/components/settings/OrganizationSection'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input, Textarea } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { describeUserAgent, deviceLabel } from '@/lib/userAgent'
import { formatPhone, isValidPhone } from '@/lib/validation'
import { useAuthStore } from '@/stores/auth'
import { useUIStore, type Lang, type Theme } from '@/stores/ui'

type Section = 'profile' | 'appearance' | 'sessions' | 'organization' | 'notifications'

export function SettingsPage() {
  const t = useT()
  const [section, setSection] = useState<Section>('profile')
  const { theme, setTheme, lang, setLang } = useUIStore()
  const canViewOrg = useAuthStore((s) => s.can('organization.view'))

  const sections: { id: Section; label: string }[] = [
    { id: 'profile', label: t('settings.profile') },
    { id: 'appearance', label: t('settings.appearance') },
    { id: 'sessions', label: t('settings.sessions') },
    ...(canViewOrg
      ? [{ id: 'organization' as const, label: t('settings.organization') }]
      : []),
    { id: 'notifications', label: t('settings.notifications') },
  ]

  const themes: { value: Theme; label: string; icon: typeof Sun }[] = [
    { value: 'light', label: t('settings.theme_light'), icon: Sun },
    { value: 'dark', label: t('settings.theme_dark'), icon: Moon },
    { value: 'system', label: t('settings.theme_system'), icon: Monitor },
  ]

  return (
    <div className="space-y-5 p-8">
      <PageHeader title={t('settings.title')} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[200px_1fr]">
        <nav className="space-y-0.5">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={cn(
                'block w-full rounded-lg px-3 py-2 text-left text-[13px] font-medium transition-colors',
                section === s.id ? 'bg-[var(--accent-10)] text-accent' : 'text-tx-2 hover:bg-surface-2',
              )}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div className="space-y-6">
          {section === 'profile' && <ProfileSection />}

          {section === 'appearance' && (
            <Card>
              <CardHeader title={t('settings.appearance')} />
              <div className="space-y-6 p-5">
                <div>
                  <p className="mb-2 text-[13px] font-medium text-tx-2">{t('settings.theme')}</p>
                  <div className="flex gap-2">
                    {themes.map((th) => (
                      <button
                        key={th.value}
                        onClick={() => {
                          setTheme(th.value)
                          authApi.switchTheme(th.value).catch(() => {})
                        }}
                        className={cn(
                          'flex flex-1 flex-col items-center gap-2 rounded-lg border py-4 transition-colors',
                          theme === th.value
                            ? 'border-accent bg-[var(--accent-10)] text-accent'
                            : 'border-line text-tx-2 hover:bg-surface-2',
                        )}
                      >
                        <th.icon className="h-5 w-5" />
                        <span className="text-[13px]">{th.label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-[13px] font-medium text-tx-2">{t('settings.language')}</p>
                  <div className="flex gap-2">
                    {(['es', 'en'] as Lang[]).map((l) => (
                      <button
                        key={l}
                        onClick={() => {
                          setLang(l)
                          authApi.switchLocale(l).catch(() => {})
                        }}
                        className={cn(
                          'rounded-lg border px-4 py-2 text-[13px] font-medium transition-colors',
                          lang === l
                            ? 'border-accent bg-[var(--accent-10)] text-accent'
                            : 'border-line text-tx-2 hover:bg-surface-2',
                        )}
                      >
                        {l === 'es' ? 'Español' : 'English'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          )}

          {section === 'sessions' && <SessionsSection />}

          {section === 'organization' && <OrganizationSection />}

          {section === 'notifications' && (
            <Card className="p-8 text-center text-sm text-tx-3">Sección en desarrollo</Card>
          )}
        </div>
      </div>
    </div>
  )
}

function SessionsSection() {
  const t = useT()
  const queryClient = useQueryClient()

  const { data: sessions, isLoading } = useQuery({
    queryKey: ['my-sessions'],
    queryFn: authApi.listSessions,
  })

  const revoke = useMutation({
    mutationFn: (id: string) => authApi.revokeSession(id),
    onSuccess: () => {
      toast(t('sessions.closed_ok'))
      queryClient.invalidateQueries({ queryKey: ['my-sessions'] })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !sessions) return <PageLoader />

  return (
    <Card>
      <CardHeader title={t('settings.sessions')} />
      <div className="p-5">
        <p className="-mt-1 mb-4 text-[13px] text-tx-3">{t('settings.sessions_hint')}</p>
        {sessions.length === 0 ? (
          <p className="py-6 text-center text-sm text-tx-3">{t('sessions.empty')}</p>
        ) : (
          <ul className="divide-y divide-line">
            {sessions.map((s) => {
              const DeviceIcon = describeUserAgent(s.user_agent).mobile ? Smartphone : Monitor
              return (
                <li key={s.id} className="flex items-center gap-4 py-3.5 first:pt-0 last:pb-0">
                  <DeviceIcon className="h-5 w-5 shrink-0 text-tx-3" />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 text-sm font-medium text-tx">
                      {deviceLabel(s.user_agent, t('sessions.unknown_device'))}
                      {s.current && <Badge tone="ok">{t('sessions.current')}</Badge>}
                    </p>
                    <p className="text-[13px] text-tx-3">
                      {[s.ip_address, `${t('sessions.started')} ${fmtDateTimeTz(s.created_at)}`]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                  </div>
                  {!s.current && (
                    <Button
                      size="sm"
                      variant="outline"
                      loading={revoke.isPending && revoke.variables === s.id}
                      onClick={() => revoke.mutate(s.id)}
                    >
                      {t('sessions.close')}
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Card>
  )
}

function ProfileSection() {
  const t = useT()
  const session = useAuthStore((s) => s.session)
  const setSession = useAuthStore((s) => s.setSession)
  const queryClient = useQueryClient()

  const { data: profile, isLoading } = useQuery({
    queryKey: ['my-profile'],
    queryFn: authApi.getMyProfile,
  })

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [bio, setBio] = useState('')
  const [phoneTouched, setPhoneTouched] = useState(false)

  function reset() {
    setName(profile?.name ?? '')
    setPhone(profile?.phone ?? '')
    setBio(profile?.bio ?? '')
    setPhoneTouched(false)
  }

  // Initialize the form once the profile loads (or after a refetch).
  useEffect(() => {
    reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile])

  const save = useMutation({
    mutationFn: () =>
      authApi.updateMyProfile({
        name,
        phone: phone || null,
        ...(profile?.role === 'doctor' ? { bio: bio || null } : {}),
      }),
    onSuccess: (updated) => {
      toast(t('settings.profile_saved'))
      queryClient.invalidateQueries({ queryKey: ['my-profile'] })
      if (session && session.name !== updated.name) {
        setSession({ ...session, name: updated.name })
      }
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !profile) return <PageLoader />

  const isDoctor = profile.role === 'doctor'
  const subtitle = [t(`role.${profile.role}`), profile.specialty].filter(Boolean).join(' · ')

  // Save/Cancel stay disabled until the user actually changes something.
  const dirty =
    name !== profile.name ||
    phone !== (profile.phone ?? '') ||
    (isDoctor && bio !== (profile.bio ?? ''))
  const phoneInvalid = !isValidPhone(phone)

  return (
    <Card>
      <CardHeader title={t('settings.profile')} />
      <form
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
        className="space-y-5 p-5"
      >
        <p className="-mt-1 text-[13px] text-tx-3">{t('settings.profile_subtitle')}</p>

        <div className="flex items-center gap-4">
          <Avatar name={name || profile.name} size="lg" />
          <div>
            <p className="text-lg font-semibold text-tx">{name || profile.name}</p>
            <p className="text-[13px] text-tx-3">{subtitle}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input label={t('users.name')} value={name} onChange={(e) => setName(e.target.value)} required />
          <Input label={t('login.email')} value={profile.email} disabled />
          <Input
            label={t('users.phone')}
            placeholder="7777-8956"
            inputMode="numeric"
            value={phone}
            onChange={(e) => setPhone(formatPhone(e.target.value))}
            onBlur={() => setPhoneTouched(true)}
            error={phoneTouched && phoneInvalid ? t('patientform.phone_invalid') : undefined}
          />
          <Input label={t('users.col_specialty')} value={profile.specialty ?? ''} disabled />
        </div>

        {isDoctor && (
          <Textarea
            label={t('settings.profile_bio')}
            rows={4}
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            maxLength={2000}
          />
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" onClick={reset} disabled={!dirty || save.isPending}>
            {t('app.cancel')}
          </Button>
          <Button
            type="submit"
            loading={save.isPending}
            disabled={!dirty || !name.trim() || phoneInvalid}
          >
            {t('app.save')}
          </Button>
        </div>
      </form>
    </Card>
  )
}

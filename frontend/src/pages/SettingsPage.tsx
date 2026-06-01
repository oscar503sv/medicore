import { useState } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { authApi } from '@/api/auth'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardHeader } from '@/components/ui/Card'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUIStore, type Lang, type Theme } from '@/stores/ui'

type Section = 'profile' | 'appearance' | 'notifications'

export function SettingsPage() {
  const t = useT()
  const [section, setSection] = useState<Section>('profile')
  const session = useAuthStore((s) => s.session)
  const { theme, setTheme, lang, setLang } = useUIStore()

  const sections: { id: Section; label: string }[] = [
    { id: 'profile', label: t('settings.profile') },
    { id: 'appearance', label: t('settings.appearance') },
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
          {section === 'profile' && (
            <Card>
              <CardHeader title={t('settings.profile')} />
              <dl className="space-y-3 p-5 text-sm">
                <div className="flex justify-between">
                  <dt className="text-tx-3">Nombre</dt>
                  <dd className="text-tx">{session?.name}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-tx-3">{t('users.col_role')}</dt>
                  <dd className="text-tx">{t(`role.${session?.role}`)}</dd>
                </div>
              </dl>
            </Card>
          )}

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

          {section === 'notifications' && (
            <Card className="p-8 text-center text-sm text-tx-3">Sección en desarrollo</Card>
          )}
        </div>
      </div>
    </div>
  )
}

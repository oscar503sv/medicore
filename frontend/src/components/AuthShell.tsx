import { type CSSProperties, type ReactNode } from 'react'
import {
  Activity,
  Calendar,
  ClipboardList,
  Heart,
  Hospital,
  Monitor,
  Moon,
  Pill,
  Shield,
  Stethoscope,
  Sun,
  Syringe,
  Users,
} from 'lucide-react'
import { Lock, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { useUIStore, type Theme } from '@/stores/ui'

/** Ambient floating health icons — position/rotation/delay per design spec. */
const FLOATERS = [
  { Icon: Stethoscope, top: '12%', left: '14%', size: 30, rot: -12, delay: 0 },
  { Icon: Heart, top: '22%', left: '82%', size: 26, rot: 10, delay: 0.6 },
  { Icon: Pill, top: '68%', left: '10%', size: 24, rot: 14, delay: 1.2 },
  { Icon: Activity, top: '78%', left: '86%', size: 32, rot: -8, delay: 0.3 },
  { Icon: Syringe, top: '44%', left: '6%', size: 22, rot: 22, delay: 1.5 },
  { Icon: Hospital, top: '8%', left: '62%', size: 24, rot: 8, delay: 0.9 },
  { Icon: Shield, top: '86%', left: '44%', size: 22, rot: -14, delay: 1.8 },
  { Icon: Calendar, top: '36%', left: '90%', size: 22, rot: -6, delay: 2.1 },
  { Icon: ClipboardList, top: '58%', left: '92%', size: 20, rot: 12, delay: 0.45 },
  { Icon: Users, top: '90%', left: '20%', size: 22, rot: 6, delay: 1.05 },
] as const

const themeIcons: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Monitor }

export function AuthShell({ children }: { children: ReactNode }) {
  const { theme, setTheme, lang, setLang } = useUIStore()
  const ThemeIcon = themeIcons[theme]
  const cycleTheme = () => {
    const order: Theme[] = ['light', 'dark', 'system']
    setTheme(order[(order.indexOf(theme) + 1) % order.length])
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-bg p-6">
      <div className="login-grid" aria-hidden />
      <div className="login-glow" aria-hidden />

      {FLOATERS.map(({ Icon, top, left, size, rot, delay }, i) => (
        <Icon
          key={i}
          aria-hidden
          strokeWidth={1.5}
          className="login-floater"
          style={
            {
              top,
              left,
              width: size,
              height: size,
              '--rot': `${rot}deg`,
              animationDelay: `${delay}s`,
            } as CSSProperties
          }
        />
      ))}

      {/* Language + theme controls (top-right, outside the card) */}
      <div className="absolute right-6 top-6 z-10 flex items-center gap-1.5">
        <div className="flex items-center rounded-pill border border-line bg-surface p-0.5">
          {(['es', 'en'] as const).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLang(l)}
              aria-pressed={lang === l}
              className={cn(
                'rounded-pill px-2.5 py-1 text-xs font-medium transition-colors',
                lang === l ? 'bg-surface-2 text-tx' : 'text-tx-3 hover:text-tx',
              )}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={cycleTheme}
          aria-label="Cambiar tema"
          className="rounded-md border border-line bg-surface p-2 text-tx-3 transition-colors hover:bg-surface-2 hover:text-tx"
        >
          <ThemeIcon className="h-[18px] w-[18px]" />
        </button>
      </div>

      <div className="relative z-10 w-full max-w-[400px]">{children}</div>
    </div>
  )
}

/** Glass-style centered card that holds the auth form. */
export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[18px] border border-line bg-surface p-9 shadow-lg">{children}</div>
  )
}

/** Brand mark + wordmark + security badge, centered at the top of the card. */
export function AuthBrand({ badge }: { badge: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-bg font-serif text-xl italic text-tx">
          M
        </span>
        <span className="font-serif text-[26px] leading-none text-tx">
          M<em className="italic text-accent">edicore</em>
        </span>
      </div>
      <span className="inline-flex items-center gap-1.5 rounded-pill border border-line bg-bg px-2.5 py-1 text-xs text-tx-2">
        <ShieldCheck className="h-3.5 w-3.5 text-ok" />
        {badge}
      </span>
    </div>
  )
}

/** Single-line compliance footer: 🔒 encryption │ HIPAA / GDPR │ SOC 2 */
export function ComplianceRow() {
  const t = useT()
  return (
    <div className="mt-7 flex items-center justify-center gap-2.5 whitespace-nowrap border-t border-line pt-4 text-[11px] text-tx-3">
      <span className="flex items-center gap-1.5">
        <Lock className="h-3 w-3 text-accent" />
        {t('login.compliance')}
      </span>
    </div>
  )
}

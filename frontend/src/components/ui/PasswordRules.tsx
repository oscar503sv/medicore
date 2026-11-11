import { Check, Circle } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'
import { PASSWORD_MIN, checkPassword, type PasswordRule } from '@/lib/passwordPolicy'

const RULES: PasswordRule[] = ['length', 'mix', 'personal']

/** Live checklist of the password policy under a password field. */
export function PasswordRules({
  password,
  personal = [],
}: {
  password: string
  personal?: (string | null | undefined)[]
}) {
  const t = useT()
  const result = checkPassword(password, personal)
  return (
    <ul className="mt-1.5 space-y-0.5 text-xs" aria-live="polite">
      {RULES.map((rule) => {
        const ok = password.length > 0 && result[rule]
        return (
          <li key={rule} className={cn('flex items-center gap-1.5', ok ? 'text-ok' : 'text-tx-3')}>
            {ok ? <Check className="h-3 w-3" /> : <Circle className="h-2.5 w-2.5" />}
            {t(`pwd.rule_${rule}`).replace('{min}', String(PASSWORD_MIN))}
          </li>
        )
      })}
      <li className="text-tx-4">{t('pwd.rule_common')}</li>
    </ul>
  )
}

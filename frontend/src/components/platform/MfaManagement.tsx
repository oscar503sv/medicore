import { useState } from 'react'
import { platformAuthApi } from '@/api/platform'
import { MfaPasswordCodeForm } from '@/components/platform/MfaPasswordCodeForm'
import { RecoveryCodesPanel } from '@/components/platform/RecoveryCodesPanel'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'

type Mode = 'idle' | 'regenerate' | 'disable' | 'codes'

/** Low-water mark: below this the admin is nudged to generate a new set. */
const LOW_CODES = 3

interface MfaManagementProps {
  account: string
  recoveryCodesRemaining: number
  /** The server-side state changed; the profile must be reloaded. */
  onChanged: () => void
}

/** What an admin with two-step verification on can do: new recovery codes, or turn it off. */
export function MfaManagement({ account, recoveryCodesRemaining, onChanged }: MfaManagementProps) {
  const t = useT()
  const [mode, setMode] = useState<Mode>('idle')
  const [codes, setCodes] = useState<string[]>([])

  async function handleRegenerate(password: string, code: string) {
    setCodes(await platformAuthApi.mfaRegenerate(password, code))
    setMode('codes')
    toast(t('sec.regenerated_ok'))
  }

  async function handleDisable(password: string, code: string) {
    await platformAuthApi.mfaDisable(password, code)
    toast(t('sec.disabled_ok'))
    onChanged()
  }

  function handleCodesDone() {
    setCodes([])
    setMode('idle')
    onChanged()
  }

  if (mode === 'codes') {
    return <RecoveryCodesPanel codes={codes} account={account} onDone={handleCodesDone} />
  }

  if (mode === 'regenerate') {
    return (
      <MfaPasswordCodeForm
        submitLabel={t('sec.regenerate')}
        description={t('sec.regenerate_desc')}
        onSubmit={handleRegenerate}
        onCancel={() => setMode('idle')}
      />
    )
  }

  if (mode === 'disable') {
    return (
      <MfaPasswordCodeForm
        submitLabel={t('sec.disable_confirm')}
        description={t('sec.disable_warn')}
        isDanger
        onSubmit={handleDisable}
        onCancel={() => setMode('idle')}
      />
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-tx-2">
        {t('sec.remaining').replace('{n}', String(recoveryCodesRemaining))}
      </p>
      {recoveryCodesRemaining <= LOW_CODES && (
        <p role="status" className="rounded-lg bg-[var(--warn-10)] px-3 py-2 text-[13px] text-warn">
          {t('sec.low_codes')}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => setMode('regenerate')}>
          {t('sec.regenerate')}
        </Button>
        <Button type="button" variant="outline" onClick={() => setMode('disable')}>
          {t('sec.disable')}
        </Button>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Copy, Download } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { downloadTextFile, recoveryCodesFile } from '@/lib/security'

interface RecoveryCodesPanelProps {
  codes: string[]
  account: string
  onDone: () => void
}

/** One-time display of the recovery codes; the admin must confirm they were saved. */
export function RecoveryCodesPanel({ codes, account, onDone }: RecoveryCodesPanelProps) {
  const t = useT()
  const [hasSaved, setHasSaved] = useState(false)

  function handleCopy() {
    void navigator.clipboard?.writeText(codes.join('\n')).then(() => toast(t('sec.codes_copied')))
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-tx">{t('sec.codes_title')}</h3>
        <p className="mt-1 text-[13px] text-tx-3">{t('sec.codes_desc')}</p>
      </div>

      <ul
        aria-label={t('sec.codes_title')}
        className="grid grid-cols-2 gap-2 rounded-lg border border-line bg-bg p-4 font-mono text-sm text-tx"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={handleCopy}>
          <Copy className="h-3.5 w-3.5" />
          {t('sec.copy_codes')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            downloadTextFile('medicore-recovery-codes.txt', recoveryCodesFile(codes, account))
          }
        >
          <Download className="h-3.5 w-3.5" />
          {t('sec.download_codes')}
        </Button>
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-sm text-tx">
        <Checkbox checked={hasSaved} onChange={(e) => setHasSaved(e.target.checked)} />
        {t('sec.codes_saved')}
      </label>

      <Button type="button" disabled={!hasSaved} onClick={onDone}>
        {t('sec.done')}
      </Button>
    </div>
  )
}

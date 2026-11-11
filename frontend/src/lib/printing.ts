import { useT } from '@/lib/i18n'
import type { PaperSize } from '@/types'

/** Page size and margins per paper (margins become the @page margins when printing). */
export const PAPER: Record<PaperSize, { width: string; height: string; margin: string }> = {
  half_letter: { width: '5.5in', height: '8.5in', margin: '0.4in' },
  letter: { width: '8.5in', height: '11in', margin: '0.6in' },
}

const fill = (s: string, values: Record<string, string | number>) =>
  Object.entries(values).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), s)

/** ``t`` plus {placeholder} substitution. */
export function useFill() {
  const t = useT()
  return (key: string, values: Record<string, string | number>) => fill(t(key), values)
}

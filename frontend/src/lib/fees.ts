import { useAuthStore } from '@/stores/auth'

/** "25.00" → "$25.00"; null → null. Fees always show their cents. */
export function fmtFee(amount: string | null | undefined): string | null {
  if (amount === null || amount === undefined) return null
  return `$${Number(amount).toFixed(2)}`
}

/** Mirrors the backend rule: every doctor's fees with fees.manage_all, one's own with
 * fees.manage_own. */
export function useCanPrice(): (doctorId: string | null | undefined) => boolean {
  const userId = useAuthStore((s) => s.session?.user_id)
  const all = useAuthStore((s) => s.can('fees.manage_all'))
  const own = useAuthStore((s) => s.can('fees.manage_own'))
  return (doctorId) => all || (own && !!doctorId && doctorId === userId)
}

/** A money input value is valid when blank or a non-negative amount with up to 2 decimals. */
export const FEE_PATTERN = /^\d{1,5}(\.\d{1,2})?$/

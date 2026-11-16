import type { VaccinePrice } from '@/api/fees'
import type { VaccineSupply } from '@/api/vaccinations'

/** Price of each vaccine the clinic has priced, by vaccine code ("25.00"). */
export function priceMap(items: VaccinePrice[] | undefined): Map<string, string> {
  const map = new Map<string, string>()
  for (const i of items ?? []) if (i.price !== null) map.set(i.vaccine_code, i.price)
  return map
}

export interface DoseLine {
  vaccine: string
  supply: VaccineSupply | ''
}

/** What a visit adds up to, in cents to avoid float drift. The server decides the real
 * charge; this is only the preview the nurse sees before saving. */
export function visitTotal(
  lines: DoseLine[],
  prices: Map<string, string>,
): { cents: number; minsal: number } {
  let cents = 0
  let minsal = 0
  for (const l of lines) {
    if (l.supply === 'minsal') minsal += 1
    else if (l.supply === 'clinic') cents += Math.round(Number(prices.get(l.vaccine) ?? 0) * 100)
  }
  return { cents, minsal }
}

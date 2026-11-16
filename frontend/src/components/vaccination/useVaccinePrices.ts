import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { vaccinePricesApi } from '@/api/fees'
import { priceMap } from '@/lib/vaccineFees'

/** The clinic's vaccine prices, shared by every screen that records or shows a dose. */
export function useVaccinePrices(enabled = true) {
  const query = useQuery({
    queryKey: ['vaccine-prices'],
    queryFn: vaccinePricesApi.list,
    enabled,
  })
  const prices = useMemo(() => priceMap(query.data?.items), [query.data])
  return {
    prices,
    isLoading: query.isLoading,
    isFailed: query.isError,
    isEmpty: query.isSuccess && prices.size === 0,
  }
}

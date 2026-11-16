import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import {
  vaccinationsApi,
  type DoseState,
  type InjectionSite,
  type VaccinationCatalog,
  type VaccineRoute,
  type VaccineSupply,
} from '@/api/vaccinations'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { openDoses } from '@/lib/vaccination'
import { visitTotal } from '@/lib/vaccineFees'
import { useVaccinePrices } from './useVaccinePrices'

export interface VisitTarget {
  appointmentId: string
  patientId: string
  patientName: string | null
}

export interface DoseRow {
  uid: number
  vaccine: string
  doseKey: string
  lot: string
  route: VaccineRoute | ''
  site: InjectionSite | ''
  supply: VaccineSupply | ''
}

/** A vaccine outside the national scheme is only ever private; in the scheme either can
 * apply, so the nurse chooses. */
const defaultSupply = (catalog: VaccinationCatalog, vaccine: string): VaccineSupply | '' =>
  catalog.vaccines.find((v) => v.code === vaccine)?.in_schedule === false ? 'clinic' : ''

/** A row starts on the most pressing dose (overdue, then due, then due soon). */
function firstRow(uid: number, catalog: VaccinationCatalog, states: DoseState[]): DoseRow {
  const pressing = (['overdue', 'due', 'due_soon'] as const)
    .map((st) => states.find((s) => s.status === st))
    .find(Boolean)
  const dose = pressing && catalog.doses.find((d) => d.key === pressing.key)
  const vaccine = dose?.vaccine ?? catalog.vaccines[0]?.code ?? ''
  return {
    uid,
    vaccine,
    doseKey: dose?.key ?? '',
    lot: '',
    route: '',
    site: '',
    supply: defaultSupply(catalog, vaccine),
  }
}

/** State and submission of a vaccination visit: several doses recorded against one appointment. */
export function useVaccinationVisit(target: VisitTarget | null, onDone: () => void) {
  const t = useT()
  const qc = useQueryClient()
  const open = target !== null
  const nextUid = useRef(1)
  const [rows, setRows] = useState<DoseRow[]>([])
  const [error, setError] = useState<string | null>(null)

  const catalogQuery = useQuery({
    queryKey: ['vaccination-catalog'],
    queryFn: vaccinationsApi.catalog,
    staleTime: Infinity,
    enabled: open,
  })
  const cardQuery = useQuery({
    queryKey: ['vaccination-card', target?.patientId],
    queryFn: () => vaccinationsApi.card(target!.patientId),
    enabled: open,
  })
  const catalog = catalogQuery.data
  const { prices, isLoading: pricesLoading, isFailed: pricesFailed } = useVaccinePrices(open)
  const states = useMemo(() => cardQuery.data?.states ?? [], [cardQuery.data])

  // Start with one row each time the visit opens; a later refetch of the card must not wipe
  // what the nurse is typing.
  const ready = !!catalog && !!cardQuery.data
  useEffect(() => {
    if (!open || !ready) return
    setError(null)
    setRows([firstRow(nextUid.current++, catalog, states)])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.appointmentId, ready])

  const update = (uid: number, patch: Partial<DoseRow>) =>
    setRows((prev) => prev.map((r) => (r.uid === uid ? { ...r, ...patch } : r)))

  const pickVaccine = (uid: number, vaccine: string) =>
    update(uid, {
      vaccine,
      doseKey: catalog ? (openDoses(catalog, states, vaccine)[0]?.key ?? '') : '',
      route: '',
      supply: catalog ? defaultSupply(catalog, vaccine) : '',
    })

  const addRow = () => {
    if (catalog) setRows((prev) => [...prev, firstRow(nextUid.current++, catalog, states)])
  }
  const removeRow = (uid: number) => setRows((prev) => prev.filter((r) => r.uid !== uid))

  // A private dose needs the clinic's price: the server refuses it otherwise.
  const isValid =
    rows.length > 0 &&
    rows.every(
      (r) =>
        r.vaccine && r.lot.trim() && r.supply && (r.supply === 'minsal' || prices.has(r.vaccine)),
    )
  const total = visitTotal(rows, prices)

  const save = useMutation({
    mutationFn: () =>
      vaccinationsApi.recordVisit({
        appointment_id: target!.appointmentId,
        patient_id: target!.patientId,
        doses: rows.map((r) => ({
          vaccine_code: r.vaccine,
          dose_key: r.doseKey || null,
          outcome: 'administered' as const,
          lot: r.lot.trim(),
          route: r.route || catalog?.vaccines.find((v) => v.code === r.vaccine)?.route || null,
          site: r.site || null,
          supply: r.supply as VaccineSupply,
        })),
      }),
    onSuccess: (result) => {
      for (const key of ['appointments', 'schedule', 'dashboard', 'vaccination-worklist']) {
        qc.invalidateQueries({ queryKey: [key] })
      }
      qc.invalidateQueries({ queryKey: ['vaccination-card', target?.patientId] })
      toast(
        result.fee === null
          ? t('vax.visit_ok')
          : t('vax.visit_ok_fee').replace('{total}', `$${Number(result.fee).toFixed(2)}`),
      )
      onDone()
    },
    onError: (err) => {
      const message = errorMessage(err)
      setError(message)
      toast(message, 'danger')
      // The appointment may have been closed by someone else: show its real state.
      qc.invalidateQueries({ queryKey: ['appointments'] })
    },
  })

  return {
    catalog,
    states,
    rows,
    error,
    prices,
    total,
    isLoading: catalogQuery.isLoading || cardQuery.isLoading || pricesLoading,
    isFailed: catalogQuery.isError || cardQuery.isError || pricesFailed,
    isValid,
    isSaving: save.isPending,
    update,
    pickVaccine,
    addRow,
    removeRow,
    submit: () => save.mutate(),
  }
}

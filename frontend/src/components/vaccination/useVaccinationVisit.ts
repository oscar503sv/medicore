import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/api/client'
import {
  vaccinationsApi,
  type DoseState,
  type InjectionSite,
  type VaccinationCatalog,
  type VaccineRoute,
} from '@/api/vaccinations'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { openDoses } from '@/lib/vaccination'

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
}

/** A row starts on the most pressing dose (overdue, then due, then due soon). */
function firstRow(uid: number, catalog: VaccinationCatalog, states: DoseState[]): DoseRow {
  const pressing = (['overdue', 'due', 'due_soon'] as const)
    .map((st) => states.find((s) => s.status === st))
    .find(Boolean)
  const dose = pressing && catalog.doses.find((d) => d.key === pressing.key)
  return {
    uid,
    vaccine: dose?.vaccine ?? catalog.vaccines[0]?.code ?? '',
    doseKey: dose?.key ?? '',
    lot: '',
    route: '',
    site: '',
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
    })

  const addRow = () => {
    if (catalog) setRows((prev) => [...prev, firstRow(nextUid.current++, catalog, states)])
  }
  const removeRow = (uid: number) => setRows((prev) => prev.filter((r) => r.uid !== uid))

  const isValid = rows.length > 0 && rows.every((r) => r.vaccine && r.lot.trim())

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
        })),
      }),
    onSuccess: () => {
      for (const key of ['appointments', 'schedule', 'dashboard', 'vaccination-worklist']) {
        qc.invalidateQueries({ queryKey: [key] })
      }
      qc.invalidateQueries({ queryKey: ['vaccination-card', target?.patientId] })
      toast(t('vax.visit_ok'))
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
    isLoading: catalogQuery.isLoading || cardQuery.isLoading,
    isFailed: catalogQuery.isError || cardQuery.isError,
    isValid,
    isSaving: save.isPending,
    update,
    pickVaccine,
    addRow,
    removeRow,
    submit: () => save.mutate(),
  }
}

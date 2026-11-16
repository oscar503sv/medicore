import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { useT } from '@/lib/i18n'
import { VisitDoseRow } from './VisitDoseRow'
import { VisitTotal } from './VisitTotal'
import { useVaccinationVisit, type VisitTarget } from './useVaccinationVisit'

export type { VisitTarget }

const MAX_DOSES = 20

/**
 * Records the doses given in a vaccination appointment and closes it. Vaccines are charged
 * per applied dose, so every dose is given here and carries its lot.
 */
export function VaccinationVisitModal({
  target,
  onClose,
}: {
  /** null = closed. */
  target: VisitTarget | null
  onClose: () => void
}) {
  const t = useT()
  const v = useVaccinationVisit(target, onClose)
  const { catalog } = v

  return (
    <Modal open={target !== null} onClose={onClose} title={t('vax.visit_title')} width="max-w-xl">
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          if (v.isValid) v.submit()
        }}
      >
        {target?.patientName && <p className="text-sm font-medium text-tx">{target.patientName}</p>}
        <p className="text-[13px] text-tx-3">{t('vax.visit_hint')}</p>

        {v.isLoading || !catalog ? (
          v.isFailed ? (
            <p role="alert" className="py-6 text-center text-sm text-danger">
              {t('vax.visit_load_error')}
            </p>
          ) : (
            <PageLoader />
          )
        ) : (
          <>
            {v.rows.map((row, i) => (
              <VisitDoseRow
                key={row.uid}
                index={i}
                row={row}
                catalog={catalog}
                states={v.states}
                prices={v.prices}
                canRemove={v.rows.length > 1}
                onChange={(patch) => v.update(row.uid, patch)}
                onVaccine={(code) => v.pickVaccine(row.uid, code)}
                onRemove={() => v.removeRow(row.uid)}
              />
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={v.rows.length >= MAX_DOSES}
              onClick={v.addRow}
            >
              <Plus className="h-4 w-4" />
              {t('vax.visit_add_dose')}
            </Button>
            <VisitTotal cents={v.total.cents} minsal={v.total.minsal} />
          </>
        )}

        {v.error && (
          <p role="alert" className="text-sm text-danger">
            {v.error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" variant="accent" loading={v.isSaving} disabled={!v.isValid}>
            {t('vax.visit_save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

import { useState } from 'react'
import { Siren } from 'lucide-react'
import { WalkInModal } from '@/components/appointments/WalkInModal'
import { Button } from '@/components/ui/Button'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Patient } from '@/types'

/** "See now": registers a patient without a booked slot. Hidden without the permission. */
export function WalkInButton({
  patient,
  variant = 'outline',
}: {
  /** From a patient's page: the patient is already known. */
  patient?: Patient
  variant?: 'outline' | 'accent'
}) {
  const t = useT()
  const canWalkIn = useAuthStore((s) => s.can('appointments.walk_in'))
  const [open, setOpen] = useState(false)
  if (!canWalkIn) return null
  return (
    <>
      <Button variant={variant} onClick={() => setOpen(true)}>
        <Siren className="h-4 w-4" />
        {t('appt.walk_in_cta')}
      </Button>
      <WalkInModal open={open} onClose={() => setOpen(false)} patient={patient} />
    </>
  )
}

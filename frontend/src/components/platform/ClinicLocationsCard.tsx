import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { MapPin, Plus } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformTenantsApi } from '@/api/platform'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Location } from '@/types'

/** Platform console: a clinic's sites. The clinic can open them itself within its plan's
 * limit; support can do it from here too (same limit). */
export function ClinicLocationsCard({
  tenantId,
  locations,
  onSaved,
}: {
  tenantId: string
  locations: Location[]
  onSaved: () => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')

  const close = () => {
    setOpen(false)
    setName('')
    setAddress('')
  }

  const add = useMutation({
    mutationFn: () =>
      platformTenantsApi.addLocation(tenantId, { name, address: address.trim() || null }),
    onSuccess: () => {
      toast(t('org.location_added_ok'))
      onSaved()
      close()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Card>
      <CardHeader
        title={t('org.locations')}
        action={
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            {t('org.add_location')}
          </Button>
        }
      />
      <div className="divide-y divide-line-soft">
        {locations.map((loc) => (
          <div key={loc.id} className="flex items-center gap-3 px-5 py-3">
            <MapPin className="h-4 w-4 text-tx-3" />
            <div>
              <p className="flex items-center gap-2 text-sm font-medium text-tx">
                {loc.name}
                {loc.is_primary && <Badge tone="accent">{t('org.location_primary')}</Badge>}
              </p>
              {loc.address && <p className="text-xs text-tx-3">{loc.address}</p>}
            </div>
          </div>
        ))}
      </div>

      <Modal open={open} onClose={close} title={t('org.add_location')} width="max-w-md">
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate()
          }}
        >
          <Input
            label={t('org.location_name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            label={t('org.location_address')}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={close}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" loading={add.isPending} disabled={!name.trim()}>
              {t('app.save')}
            </Button>
          </div>
        </form>
      </Modal>
    </Card>
  )
}

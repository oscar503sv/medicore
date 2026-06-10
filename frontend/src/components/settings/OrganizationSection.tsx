import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MapPin, Pencil, Plus } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { organizationApi } from '@/api/organization'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Location, Organization } from '@/types'

export function OrganizationSection() {
  const t = useT()
  const qc = useQueryClient()
  const canManage = useAuthStore((s) => s.can('organization.manage'))

  const { data: org, isLoading } = useQuery({
    queryKey: ['organization'],
    queryFn: organizationApi.get,
  })

  const [legalName, setLegalName] = useState('')
  const [taxId, setTaxId] = useState('')
  const [timezone, setTimezone] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Location | null>(null)

  useEffect(() => {
    if (org) {
      setLegalName(org.legal_name)
      setTaxId(org.tax_id)
      setTimezone(org.timezone)
    }
  }, [org])

  const applyResult = (data: Organization) => qc.setQueryData(['organization'], data)

  const save = useMutation({
    mutationFn: () =>
      organizationApi.update({ legal_name: legalName, tax_id: taxId, timezone }),
    onSuccess: (data) => {
      applyResult(data)
      toast(t('org.saved_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !org) return <PageLoader />

  const dirty =
    legalName !== org.legal_name || taxId !== org.tax_id || timezone !== org.timezone

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={t('settings.organization')} />
        <div className="space-y-4 p-5">
          <p className="text-[13px] text-tx-3">{t('org.subtitle')}</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={t('org.legal_name')}
              value={legalName}
              disabled={!canManage}
              onChange={(e) => setLegalName(e.target.value)}
            />
            <Input
              label={t('org.tax_id')}
              value={taxId}
              disabled={!canManage}
              onChange={(e) => setTaxId(e.target.value)}
            />
            <Input
              label={t('org.timezone')}
              value={timezone}
              disabled={!canManage}
              placeholder="America/Mexico_City"
              onChange={(e) => setTimezone(e.target.value)}
            />
            <Input label={t('org.slug')} value={org.slug} disabled />
            <Input label={t('org.plan')} value={org.plan} disabled />
            <Input label={t('org.seat_limit')} value={String(org.seat_limit)} disabled />
          </div>
          {canManage && (
            <div className="flex justify-end">
              <Button
                loading={save.isPending}
                disabled={!dirty || !legalName.trim()}
                onClick={() => save.mutate()}
              >
                {t('app.save')}
              </Button>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title={t('org.locations')}
          action={
            canManage ? (
              <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
                <Plus className="h-3.5 w-3.5" />
                {t('org.add_location')}
              </Button>
            ) : undefined
          }
        />
        <div className="divide-y divide-line-soft">
          {org.locations.map((loc) => (
            <div key={loc.id} className="flex items-center justify-between px-5 py-3.5">
              <div className="flex items-center gap-3">
                <MapPin className="h-4 w-4 text-tx-3" />
                <div>
                  <p className="flex items-center gap-2 text-sm font-medium text-tx">
                    {loc.name}
                    {loc.is_primary && <Badge tone="accent">{t('org.location_primary')}</Badge>}
                  </p>
                  {loc.address && <p className="text-xs text-tx-3">{loc.address}</p>}
                </div>
              </div>
              {canManage && (
                <Button size="sm" variant="ghost" onClick={() => setEditTarget(loc)}>
                  <Pencil className="h-3.5 w-3.5" />
                  {t('app.edit')}
                </Button>
              )}
            </div>
          ))}
        </div>
      </Card>

      <LocationModal
        open={addOpen}
        location={null}
        onClose={() => setAddOpen(false)}
        onSaved={applyResult}
      />
      <LocationModal
        open={!!editTarget}
        location={editTarget}
        onClose={() => setEditTarget(null)}
        onSaved={applyResult}
      />
    </div>
  )
}

function LocationModal({
  open,
  location,
  onClose,
  onSaved,
}: {
  open: boolean
  location: Location | null
  onClose: () => void
  onSaved: (org: Organization) => void
}) {
  const t = useT()
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [isPrimary, setIsPrimary] = useState(false)

  useEffect(() => {
    if (open) {
      setName(location?.name ?? '')
      setAddress(location?.address ?? '')
      setIsPrimary(location?.is_primary ?? false)
    }
  }, [open, location])

  const save = useMutation({
    mutationFn: () =>
      location
        ? organizationApi.updateLocation(location.id, { name, address })
        : organizationApi.addLocation({ name, address, is_primary: isPrimary }),
    onSuccess: (data) => {
      onSaved(data)
      toast(t(location ? 'org.location_updated_ok' : 'org.location_added_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t(location ? 'org.edit_location' : 'org.add_location')}
      width="max-w-md"
    >
      <div className="space-y-4 p-5">
        <Input
          label={t('org.location_name')}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          label={t('org.location_address')}
          value={address}
          onChange={(e) => setAddress(e.target.value)}
        />
        {!location && (
          <label className="flex cursor-pointer items-center gap-2 text-sm text-tx-2">
            <Checkbox checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
            {t('org.location_primary')}
          </label>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>
            {t('app.save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

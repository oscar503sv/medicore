import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Building2, CheckCircle2, Plus, Ban } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformTenantsApi, type CreateTenantPayload } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import { TIMEZONES } from '@/lib/timezones'
import type { TenantStatus } from '@/types'

const STATUS_TONE: Record<TenantStatus, 'ok' | 'danger' | 'neutral'> = {
  active: 'ok',
  suspended: 'danger',
  archived: 'neutral',
}

function genPassword(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
  return Array.from({ length: 12 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

export function ClinicsListPage() {
  const t = useT()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['platform-tenants'],
    queryFn: () => platformTenantsApi.list({ limit: 200 }),
  })

  if (isLoading || !data) return <PageLoader />

  const tenants = data.items
  const active = tenants.filter((c) => c.status === 'active').length
  const suspended = tenants.filter((c) => c.status === 'suspended').length

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t('platform.clinics_title')}
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            {t('platform.new_clinic')}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Building2} label={t('platform.total_clinics')} value={String(data.total)} />
        <StatCard icon={CheckCircle2} label={t('platform.active_clinics')} value={String(active)} />
        <StatCard icon={Ban} label={t('platform.suspended_clinics')} value={String(suspended)} />
      </div>

      <Card>
        <Table>
          <thead>
            <Tr>
              <Th>{t('platform.col_name')}</Th>
              <Th>{t('platform.col_slug')}</Th>
              <Th>{t('platform.col_plan')}</Th>
              <Th>CIE</Th>
              <Th>{t('platform.col_status')}</Th>
            </Tr>
          </thead>
          <tbody>
            {tenants.map((c) => (
              <Tr key={c.id} onClick={() => navigate(`/platform/clinics/${c.id}`)}>
                <Td className="font-medium text-tx">{c.legal_name}</Td>
                <Td className="font-mono text-[13px]">{c.slug}</Td>
                <Td>{c.plan}</Td>
                <Td className="uppercase">{c.icd_version}</Td>
                <Td>
                  <Badge tone={STATUS_TONE[c.status]}>{t(`platform.status_${c.status}`)}</Badge>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <CreateClinicModal open={creating} onClose={() => setCreating(false)} />
    </div>
  )
}

function CreateClinicModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const qc = useQueryClient()
  const empty: CreateTenantPayload = {
    legal_name: '',
    tax_id: '',
    slug: '',
    timezone: 'America/El_Salvador',
    icd_version: 'cie11',
    location_name: '',
    admin_name: '',
    admin_email: '',
    admin_password: genPassword(),
  }
  const [form, setForm] = useState<CreateTenantPayload>(empty)
  const set = (patch: Partial<CreateTenantPayload>) => setForm((f) => ({ ...f, ...patch }))

  const create = useMutation({
    mutationFn: () => platformTenantsApi.create(form),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['platform-tenants'] })
      toast(
        `${t('platform.created_ok')} · ${res.admin_email} / ${form.admin_password}`,
      )
      setForm({ ...empty, admin_password: genPassword() })
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('platform.new_clinic')} width="max-w-xl">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
        className="space-y-4 p-5"
      >
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('platform.f_legal_name')}
            value={form.legal_name}
            onChange={(e) => set({ legal_name: e.target.value })}
            required
          />
          <Input
            label={t('platform.f_tax_id')}
            value={form.tax_id}
            onChange={(e) => set({ tax_id: e.target.value })}
            required
          />
          <Input
            label={t('platform.f_slug')}
            value={form.slug}
            onChange={(e) => set({ slug: e.target.value.toLowerCase() })}
            placeholder="clinica-norte"
            required
          />
          <Select
            label={t('platform.f_icd')}
            value={form.icd_version}
            onChange={(e) => set({ icd_version: e.target.value })}
          >
            <option value="cie11">CIE-11</option>
            <option value="cie10">CIE-10</option>
          </Select>
          <Input
            label={t('platform.f_location')}
            value={form.location_name}
            onChange={(e) => set({ location_name: e.target.value })}
            placeholder="Madrid · Atocha"
            required
          />
          <Select
            label={t('platform.f_timezone')}
            value={form.timezone}
            onChange={(e) => set({ timezone: e.target.value })}
          >
            {TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>
                {tz.label}
              </option>
            ))}
          </Select>
        </div>

        <div className="rounded-lg border border-line bg-surface-2 p-4">
          <p className="mb-3 text-[13px] font-semibold text-tx">{t('platform.first_admin')}</p>
          <div className="grid grid-cols-2 gap-4">
            <Input
              label={t('platform.f_admin_name')}
              value={form.admin_name}
              onChange={(e) => set({ admin_name: e.target.value })}
              required
            />
            <Input
              label={t('platform.f_admin_email')}
              type="email"
              value={form.admin_email}
              onChange={(e) => set({ admin_email: e.target.value })}
              required
            />
          </div>
          <div className="mt-4 flex items-end gap-2">
            <div className="flex-1">
              <Input
                label={t('platform.f_temp_password')}
                value={form.admin_password}
                onChange={(e) => set({ admin_password: e.target.value })}
                required
                minLength={8}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => set({ admin_password: genPassword() })}
            >
              {t('platform.generate')}
            </Button>
          </div>
          <p className="mt-1.5 text-xs text-tx-3">{t('platform.temp_password_hint')}</p>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" loading={create.isPending}>
            {t('platform.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

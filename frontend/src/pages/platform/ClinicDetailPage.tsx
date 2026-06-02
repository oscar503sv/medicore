import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { platformTenantsApi } from '@/api/platform'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { TenantStatus } from '@/types'

const STATUS_TONE: Record<TenantStatus, 'ok' | 'danger' | 'neutral'> = {
  active: 'ok',
  suspended: 'danger',
  archived: 'neutral',
}

export function ClinicDetailPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { id = '' } = useParams()

  const { data: clinic, isLoading } = useQuery({
    queryKey: ['platform-tenant', id],
    queryFn: () => platformTenantsApi.get(id),
  })

  const [legalName, setLegalName] = useState('')
  const [taxId, setTaxId] = useState('')
  const [plan, setPlan] = useState('')
  const [seatLimit, setSeatLimit] = useState(10)
  const [icdVersion, setIcdVersion] = useState('cie11')

  useEffect(() => {
    if (clinic) {
      setLegalName(clinic.legal_name)
      setTaxId(clinic.tax_id)
      setPlan(clinic.plan)
      setSeatLimit(clinic.seat_limit)
      setIcdVersion(clinic.icd_version)
    }
  }, [clinic])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['platform-tenant', id] })
    qc.invalidateQueries({ queryKey: ['platform-tenants'] })
  }

  const save = useMutation({
    mutationFn: () =>
      platformTenantsApi.update(id, {
        legal_name: legalName,
        tax_id: taxId,
        plan,
        seat_limit: seatLimit,
        icd_version: icdVersion,
      }),
    onSuccess: () => {
      toast(t('platform.saved_ok'))
      invalidate()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const setStatus = useMutation({
    mutationFn: (status: string) => platformTenantsApi.setStatus(id, status),
    onSuccess: () => {
      toast(t('platform.status_changed_ok'))
      invalidate()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  if (isLoading || !clinic) return <PageLoader />

  return (
    <div className="space-y-5 p-8">
      <button
        onClick={() => navigate('/platform/clinics')}
        className="flex items-center gap-1.5 text-[13px] text-tx-3 hover:text-tx"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('platform.back_to_clinics')}
      </button>

      <PageHeader
        eyebrow={clinic.slug}
        title={clinic.legal_name}
        action={<Badge tone={STATUS_TONE[clinic.status]}>{t(`platform.status_${clinic.status}`)}</Badge>}
      />

      <Card>
        <CardHeader title={t('platform.clinic_info')} />
        <form
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
          className="space-y-4 p-5"
        >
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('platform.f_legal_name')} value={legalName} onChange={(e) => setLegalName(e.target.value)} required />
            <Input label={t('platform.f_tax_id')} value={taxId} onChange={(e) => setTaxId(e.target.value)} required />
            <Input label={t('platform.f_plan')} value={plan} onChange={(e) => setPlan(e.target.value)} />
            <Input
              label={t('platform.f_seat_limit')}
              type="number"
              min={1}
              value={seatLimit}
              onChange={(e) => setSeatLimit(Number(e.target.value))}
            />
            <Select label={t('platform.f_icd')} value={icdVersion} onChange={(e) => setIcdVersion(e.target.value)}>
              <option value="cie11">CIE-11</option>
              <option value="cie10">CIE-10</option>
            </Select>
            <Input label={t('platform.f_slug')} value={clinic.slug} disabled />
          </div>
          <div className="flex justify-end">
            <Button type="submit" loading={save.isPending}>
              {t('app.save')}
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <CardHeader title={t('platform.status_actions')} />
        <div className="flex flex-wrap gap-2 p-5">
          {clinic.status !== 'active' && (
            <Button variant="outline" loading={setStatus.isPending} onClick={() => setStatus.mutate('active')}>
              {t('platform.action_activate')}
            </Button>
          )}
          {clinic.status === 'active' && (
            <Button variant="outline" loading={setStatus.isPending} onClick={() => setStatus.mutate('suspended')}>
              {t('platform.action_suspend')}
            </Button>
          )}
          {clinic.status !== 'archived' && (
            <Button variant="danger" loading={setStatus.isPending} onClick={() => setStatus.mutate('archived')}>
              {t('platform.action_archive')}
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}

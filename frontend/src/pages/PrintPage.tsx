import { useEffect, useState, type ReactNode } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Printer, X } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { printApi, type PrintContext, type ProcedureDocument } from '@/api/printing'
import { vaccinationsApi } from '@/api/vaccinations'
import {
  AgendaDoc,
  AppointmentSlipDoc,
  CertificateDoc,
  ExamOrderDoc,
  PrescriptionDoc,
  ProcedureDoc,
  RecordCopyDoc,
  VaccinationCardDoc,
} from '@/components/print/documents'
import { Button } from '@/components/ui/Button'
import { Checkbox } from '@/components/ui/Checkbox'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { useT } from '@/lib/i18n'
import { PAPER } from '@/lib/printing'
import type { PaperSize } from '@/types'

/** Documents whose paper follows the clinic's setting (the rest always print on letter). */
const SHORT = new Set(['prescription', 'exams', 'certificate', 'instructions', 'appointment'])

type Loaded = {
  ctx: PrintContext
  render: (paper: PaperSize, withIndications: boolean) => ReactNode
  indications?: boolean
}

async function load(kind: string, id: string, doctor: string | null): Promise<Loaded> {
  switch (kind) {
    case 'prescription':
    case 'exams':
    case 'record': {
      const doc = await printApi.record(id, kind)
      return {
        ctx: doc.context,
        indications: kind === 'prescription' && !!doc.indications,
        render: (paper, withIndications) =>
          kind === 'prescription' ? (
            <PrescriptionDoc doc={doc} paper={paper} withIndications={withIndications} />
          ) : kind === 'exams' ? (
            <ExamOrderDoc doc={doc} paper={paper} />
          ) : (
            <RecordCopyDoc doc={doc} />
          ),
      }
    }
    case 'certificate': {
      const doc = await printApi.certificate(id)
      return { ctx: doc.context, render: (paper) => <CertificateDoc doc={doc} paper={paper} /> }
    }
    case 'instructions':
    case 'consent':
    case 'pathology': {
      const doc = await printApi.procedure(id, kind as ProcedureDocument)
      return {
        ctx: doc.context,
        render: (paper) => (
          <ProcedureDoc doc={doc} document={kind as ProcedureDocument} paper={paper} />
        ),
      }
    }
    case 'vaccination-card': {
      const [ctx, card, catalog] = await Promise.all([
        printApi.vaccinationCard(id),
        vaccinationsApi.card(id),
        vaccinationsApi.catalog(),
      ])
      return {
        ctx,
        render: () => <VaccinationCardDoc ctx={ctx} card={card} doses={catalog.doses} />,
      }
    }
    case 'appointment': {
      const doc = await printApi.appointment(id)
      return { ctx: doc.context, render: (paper) => <AppointmentSlipDoc doc={doc} paper={paper} /> }
    }
    case 'agenda': {
      const doc = await printApi.agenda(id, doctor ?? undefined)
      return { ctx: doc.context, render: () => <AgendaDoc doc={doc} /> }
    }
    default:
      throw new Error('unknown document')
  }
}

/** Print view: a toolbar (screen only) and the sheet, laid out for paper. The document is
 * fetched once (each fetch is logged as a print in the audit trail). */
export function PrintPage() {
  const t = useT()
  const { kind = '', id = '' } = useParams()
  const [params] = useSearchParams()
  const doctor = params.get('doctor')
  const { data, error, isLoading } = useQuery({
    queryKey: ['print', kind, id, doctor],
    queryFn: () => load(kind, id, doctor),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  })
  const short = SHORT.has(kind)
  const [paper, setPaper] = useState<PaperSize | null>(null)
  const [withIndications, setWithIndications] = useState(true)
  const effective: PaperSize = short ? (paper ?? data?.ctx.clinic.paper ?? 'half_letter') : 'letter'

  useEffect(() => {
    document.title = `${t(`pr.doc.${kind.replace('-', '_')}`)} · Medicore`
  }, [kind, t])

  if (isLoading) return <PageLoader />
  if (error || !data) {
    return (
      <p className="p-8 text-sm text-danger">{error ? errorMessage(error) : t('pr.not_found')}</p>
    )
  }
  const size = PAPER[effective]

  return (
    <div className="min-h-screen bg-surface-2 print:bg-white">
      <style>{`@page { size: ${size.width} ${size.height}; margin: ${size.margin}; }`}</style>
      <div className="no-print sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-line bg-surface px-5 py-3">
        <p className="mr-auto text-sm font-medium text-tx">
          {t(`pr.doc.${kind.replace('-', '_')}`)}
        </p>
        {data.indications && (
          <label className="flex items-center gap-2 text-[13px] text-tx-2">
            <Checkbox
              checked={withIndications}
              onChange={(e) => setWithIndications(e.target.checked)}
            />
            {t('pr.with_indications')}
          </label>
        )}
        {short && (
          <div className="flex items-center gap-2">
            <span className="text-[13px] text-tx-3">{t('pr.paper')}</span>
            <Segmented
              value={effective}
              onChange={setPaper}
              options={(['half_letter', 'letter'] as PaperSize[]).map((p) => ({
                value: p,
                label: t(`pr.paper.${p}`),
              }))}
            />
          </div>
        )}
        <Button variant="outline" size="sm" onClick={() => window.close()}>
          <X size={14} /> {t('pr.close')}
        </Button>
        <Button size="sm" onClick={() => window.print()}>
          <Printer size={14} /> {t('pr.print')}
        </Button>
        <p className="w-full text-right text-xs text-tx-3">{t('pr.hint')}</p>
      </div>
      {data.render(effective, withIndications)}
    </div>
  )
}

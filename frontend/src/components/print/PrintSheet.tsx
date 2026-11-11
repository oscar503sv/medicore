import type { ReactNode } from 'react'
import type { PrintContext } from '@/api/printing'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { PAPER, useFill } from '@/lib/printing'
import type { PaperSize } from '@/types'

/** The clinic's header (or, on letterhead paper, the blank space it would take). */
function ClinicHeader({ ctx, doctorInHeader }: { ctx: PrintContext; doctorInHeader: boolean }) {
  const f = useFill()
  const { clinic, doctor } = ctx
  if (clinic.letterhead) return <div style={{ height: '1.1in' }} />
  const contact = [clinic.address, clinic.phone && f('pr.phone', { v: clinic.phone })]
    .filter(Boolean)
    .join(' · ')
  return (
    <header className="flex items-start justify-between gap-4 border-b border-neutral-800 pb-2">
      <div className="min-w-0">
        <p className="text-[13pt] font-semibold leading-tight">{clinic.name}</p>
        <p className="text-[8.5pt] text-neutral-600">{clinic.location_name}</p>
        {contact && <p className="text-[8.5pt] text-neutral-600">{contact}</p>}
      </div>
      {doctorInHeader && doctor && (
        <div className="shrink-0 text-right">
          <p className="text-[10.5pt] font-semibold leading-tight">{doctor.name}</p>
          {doctor.specialty && <p className="text-[8.5pt] text-neutral-600">{doctor.specialty}</p>}
          {doctor.jvpm && (
            <p className="text-[8.5pt] text-neutral-600">{f('pr.jvpm', { v: doctor.jvpm })}</p>
          )}
        </div>
      )}
    </header>
  )
}

/** Patient line: name, age, sex, record code and the document's date. */
export function PatientStrip({
  ctx,
  date,
  showAllergies = false,
}: {
  ctx: PrintContext
  date: string
  showAllergies?: boolean
}) {
  const t = useT()
  const f = useFill()
  const p = ctx.patient
  if (!p) return null
  return (
    <section className="mt-3 text-[9.5pt]">
      <div className="flex flex-wrap gap-x-5 gap-y-0.5">
        <span>
          <span className="text-neutral-500">{t('pr.patient')}: </span>
          <span className="font-semibold">{p.name}</span>
        </span>
        <span>
          <span className="text-neutral-500">{t('pr.age')}: </span>
          {f('pr.age_years', { n: p.age })}
        </span>
        <span>
          <span className="text-neutral-500">{t('pr.sex')}: </span>
          {t(`sex.${p.sex}`)}
        </span>
        <span>
          <span className="text-neutral-500">{t('pr.code')}: </span>
          {p.code}
        </span>
        <span>
          <span className="text-neutral-500">{t('pr.date')}: </span>
          {date}
        </span>
      </div>
      {showAllergies && p.allergies.length > 0 && (
        <p className="mt-0.5">
          <span className="font-semibold">{t('pr.allergies')}: </span>
          {p.allergies.join(', ')}
        </p>
      )}
    </section>
  )
}

/** Signature line for the doctor (name, JVPM) or another signer. */
export function SignatureLine({ label, ctx }: { label?: string; ctx?: PrintContext }) {
  const t = useT()
  const f = useFill()
  const doctor = ctx?.doctor
  return (
    <div className="print-avoid-break mx-auto mt-10 w-60 text-center text-[9pt]">
      <div className="border-t border-neutral-800 pt-1">
        {doctor ? (
          <>
            <p className="font-semibold">{doctor.name}</p>
            {doctor.jvpm && <p>{f('pr.jvpm', { v: doctor.jvpm })}</p>}
            <p className="text-neutral-500">{label ?? t('pr.signature')}</p>
          </>
        ) : (
          <p className="text-neutral-500">{label ?? t('pr.signature')}</p>
        )}
      </div>
    </div>
  )
}

/** One printed sheet: header, title, body and footer. ``fill`` pushes the footer (usually
 * the signature) to the bottom of a one-page document. */
export function PrintSheet({
  ctx,
  paper,
  title,
  code,
  doctorInHeader = false,
  fillPage = false,
  children,
  footer,
}: {
  ctx: PrintContext
  paper: PaperSize
  title: string
  code?: string
  doctorInHeader?: boolean
  fillPage?: boolean
  children: ReactNode
  footer?: ReactNode
}) {
  const f = useFill()
  const size = PAPER[paper]
  // On screen the sheet previews the full page; content height excludes both margins.
  const inner = `calc(${size.height} - 2 * ${size.margin} - 0.15in)`
  return (
    <article
      className="print-sheet mx-auto my-6 shadow-lg"
      style={
        {
          width: size.width,
          minHeight: size.height,
          '--sheet-margin': size.margin,
        } as React.CSSProperties
      }
    >
      <div className="flex flex-col" style={fillPage ? { minHeight: inner } : undefined}>
        <ClinicHeader ctx={ctx} doctorInHeader={doctorInHeader} />
        <h1 className="mt-3 text-center text-[11pt] font-semibold uppercase tracking-wide">
          {title}
        </h1>
        <div className="flex-1">{children}</div>
        {footer}
        <p className="mt-4 flex justify-between text-[7.5pt] text-neutral-400">
          <span>{code ? f('pr.page_of', { code }) : ''}</span>
          <span>{f('pr.printed_at', { v: fmtDate(ctx.printed_at, 'd MMM yyyy HH:mm') })}</span>
        </p>
      </div>
    </article>
  )
}

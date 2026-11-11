import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { consultationsApi } from '@/api/consultations'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toast'
import { useT } from '@/lib/i18n'
import type { Consultation, ExamKind } from '@/types'

const KINDS: ExamKind[] = ['lab', 'imaging', 'other']

/** Common orders in a general / gynecology practice, one click to add. */
const QUICK: { name: string; kind: ExamKind }[] = [
  { name: 'Hemograma completo', kind: 'lab' },
  { name: 'Glucosa en ayunas', kind: 'lab' },
  { name: 'Perfil lipídico', kind: 'lab' },
  { name: 'Examen general de orina', kind: 'lab' },
  { name: 'Examen general de heces', kind: 'lab' },
  { name: 'Prueba de embarazo (β-hCG)', kind: 'lab' },
  { name: 'Perfil tiroideo (TSH, T4 libre)', kind: 'lab' },
  { name: 'Ultrasonografía pélvica', kind: 'imaging' },
  { name: 'Ultrasonografía transvaginal', kind: 'imaging' },
  { name: 'Ultrasonografía obstétrica', kind: 'imaging' },
  { name: 'Mamografía', kind: 'imaging' },
  { name: 'Radiografía de tórax', kind: 'imaging' },
]

const INPUT =
  'h-9 w-full rounded-lg border border-line bg-bg px-2 text-sm focus:border-accent focus:outline-none'

/** Exam orders written during the consultation; they print as the exam order once signed. */
export function ConsultationExams({
  consultationId,
  consultation,
}: {
  consultationId: string
  consultation: Consultation
}) {
  const t = useT()
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', kind: 'lab' as ExamKind, notes: '' })
  const exams = consultation.draft_exams

  const add = useMutation({
    mutationFn: (exam: { name: string; kind: ExamKind; notes?: string | null }) =>
      consultationsApi.addExam(consultationId, exam),
    onSuccess: (c) => {
      qc.setQueryData(['consultation', consultationId], c)
      setForm({ name: '', kind: form.kind, notes: '' })
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })
  const remove = useMutation({
    mutationFn: (index: number) => consultationsApi.removeExam(consultationId, index),
    onSuccess: (c) => qc.setQueryData(['consultation', consultationId], c),
  })
  const ordered = new Set(exams.map((e) => e.name))

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-tx">{t('exam.title')}</h3>
        <span className="text-xs text-tx-3">{exams.length}</span>
      </div>
      <div className="space-y-2">
        {exams.map((e, i) => (
          <div
            key={i}
            className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2"
          >
            <div className="flex-1">
              <p className="text-sm font-medium text-tx">{e.name}</p>
              <p className="text-xs text-tx-3">
                {t(`exam.kind.${e.kind}`)}
                {e.notes ? ` · ${e.notes}` : ''}
              </p>
            </div>
            <button onClick={() => remove.mutate(i)} className="text-tx-4 hover:text-danger">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-line bg-surface p-4">
        <p className="eyebrow mb-2">{t('exam.quick')}</p>
        <div className="mb-4 flex flex-wrap gap-1.5">
          {QUICK.filter((q) => !ordered.has(q.name)).map((q) => (
            <button
              key={q.name}
              type="button"
              disabled={add.isPending}
              onClick={() => add.mutate(q)}
              className="rounded-pill border border-line px-2.5 py-1 text-xs text-tx-2 hover:border-accent hover:text-accent"
            >
              + {q.name}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_140px_1fr]">
          <div>
            <label className="eyebrow mb-1 block">{t('exam.name')}</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('exam.name_ph')}
              className={INPUT}
            />
          </div>
          <div>
            <label className="eyebrow mb-1 block">{t('exam.kind')}</label>
            <select
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value as ExamKind })}
              className={INPUT}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`exam.kind.${k}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="eyebrow mb-1 block">{t('exam.notes')}</label>
            <input
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder={t('exam.notes_ph')}
              className={INPUT}
            />
          </div>
        </div>
        <Button
          size="sm"
          className="mt-3"
          disabled={!form.name.trim()}
          loading={add.isPending}
          onClick={() =>
            add.mutate({ name: form.name, kind: form.kind, notes: form.notes || null })
          }
        >
          <Plus className="h-4 w-4" />
          {t('exam.add')}
        </Button>
      </div>
    </section>
  )
}

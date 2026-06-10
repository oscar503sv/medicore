import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Upload } from 'lucide-react'
import { errorMessage } from '@/api/client'
import { recordsApi } from '@/api/records'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { fmtDateTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { DocumentKind } from '@/types'

// Mirrors the backend whitelist in UploadDocument (use_cases/records.py).
const ALLOWED_MIME = new Set([
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/webp',
  'text/plain',
])
const MAX_BYTES = 25 * 1024 * 1024

const KINDS: DocumentKind[] = ['lab', 'imaging', 'rx', 'consent', 'other']

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// storage_key must satisfy the backend pattern ^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$ (no "..").
function safeKeyName(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]/g, '_').replace(/\.{2,}/g, '.')
}

export function PatientDocuments({ patientId }: { patientId: string }) {
  const t = useT()
  const qc = useQueryClient()
  const canUpload = useAuthStore((s) => s.can('records.upload'))
  const [uploadOpen, setUploadOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState<DocumentKind>('lab')
  const fileInput = useRef<HTMLInputElement>(null)

  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents', patientId],
    queryFn: () => recordsApi.listDocuments(patientId),
  })

  const close = () => {
    setUploadOpen(false)
    setFile(null)
    setKind('lab')
  }

  const upload = useMutation({
    mutationFn: () =>
      recordsApi.uploadDocument({
        patient_id: patientId,
        file_name: file!.name,
        kind,
        mime_type: file!.type,
        size_bytes: file!.size,
        storage_key: `${patientId}/${Date.now()}-${safeKeyName(file!.name)}`,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documents', patientId] })
      toast(t('docs.uploaded_ok'))
      close()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const pickFile = (f: File | null) => {
    if (!f) return
    if (!ALLOWED_MIME.has(f.type)) {
      toast(t('docs.bad_type'), 'danger')
      return
    }
    if (f.size === 0 || f.size > MAX_BYTES) {
      toast(t('docs.bad_size'), 'danger')
      return
    }
    setFile(f)
  }

  return (
    <>
      <Card>
        {isLoading ? (
          <PageLoader />
        ) : documents && documents.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <Th>{t('docs.col_name')}</Th>
                <Th>{t('docs.kind')}</Th>
                <Th>{t('docs.col_size')}</Th>
                <Th>{t('docs.col_uploaded')}</Th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <Tr key={d.id}>
                  <Td>
                    <span className="inline-flex items-center gap-2 font-medium text-tx">
                      <FileText className="h-4 w-4 text-tx-3" />
                      {d.file_name}
                    </span>
                  </Td>
                  <Td>
                    <Badge tone="info">{t(`docs.kind_${d.kind}`)}</Badge>
                  </Td>
                  <Td>{fmtBytes(d.size_bytes)}</Td>
                  <Td>{fmtDateTimeTz(d.uploaded_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState title={t('docs.empty')} description="" />
        )}
        {canUpload && (
          <div className="flex justify-end border-t border-line p-4">
            <Button variant="outline" onClick={() => setUploadOpen(true)}>
              <Upload className="h-4 w-4" />
              {t('docs.upload')}
            </Button>
          </div>
        )}
      </Card>

      <Modal open={uploadOpen} onClose={close} title={t('docs.upload_title')} width="max-w-md">
        <div className="space-y-4 p-5">
          <p className="rounded-lg border border-line bg-surface-2/40 p-3 text-[13px] text-tx-3">
            {t('docs.metadata_notice')}
          </p>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,.txt"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
          <Button variant="outline" onClick={() => fileInput.current?.click()}>
            {t('docs.select_file')}
          </Button>
          {file && (
            <div className="rounded-lg border border-line p-3 text-sm">
              <p className="font-medium text-tx">{file.name}</p>
              <p className="text-xs text-tx-3">
                {file.type} · {fmtBytes(file.size)}
              </p>
            </div>
          )}
          <Select label={t('docs.kind')} value={kind} onChange={(e) => setKind(e.target.value as DocumentKind)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`docs.kind_${k}`)}
              </option>
            ))}
          </Select>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={close}>
              {t('app.cancel')}
            </Button>
            <Button loading={upload.isPending} disabled={!file} onClick={() => upload.mutate()}>
              {t('docs.upload')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

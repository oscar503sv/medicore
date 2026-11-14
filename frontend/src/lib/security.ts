/** Setup key in blocks of four, easier to read and type into an authenticator app. */
export function groupSecret(secret: string): string {
  return secret.replace(/(.{4})/g, '$1 ').trim()
}

export function recoveryCodesFile(codes: string[], account: string): string {
  return ['Medicore - recovery codes', account, '', ...codes, ''].join('\n')
}

export function downloadTextFile(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

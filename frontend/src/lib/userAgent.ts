// Tiny user-agent describer for the active-sessions views. Intentionally coarse:
// it only needs to help a person recognize "my laptop" vs "my phone", not fingerprint.

export interface DeviceInfo {
  browser: string | null
  os: string | null
  mobile: boolean
}

export function describeUserAgent(ua: string | null | undefined): DeviceInfo {
  if (!ua) return { browser: null, os: null, mobile: false }

  let browser: string | null = null
  if (/edg(e|a|ios)?\//i.test(ua)) browser = 'Edge'
  else if (/opr\/|opera/i.test(ua)) browser = 'Opera'
  else if (/chrome|crios/i.test(ua)) browser = 'Chrome'
  else if (/firefox|fxios/i.test(ua)) browser = 'Firefox'
  else if (/safari/i.test(ua)) browser = 'Safari'
  else if (/curl|httpie|postman/i.test(ua)) browser = 'API client'

  let os: string | null = null
  if (/windows/i.test(ua)) os = 'Windows'
  else if (/android/i.test(ua)) os = 'Android'
  else if (/iphone|ipad|ios/i.test(ua)) os = 'iOS'
  else if (/mac os|macintosh/i.test(ua)) os = 'macOS'
  else if (/linux/i.test(ua)) os = 'Linux'

  const mobile = /android|iphone|ipad|mobile/i.test(ua)
  return { browser, os, mobile }
}

export function deviceLabel(ua: string | null | undefined, fallback: string): string {
  const { browser, os } = describeUserAgent(ua)
  if (browser && os) return `${browser} · ${os}`
  return browser ?? os ?? fallback
}

import axios, { type InternalAxiosRequestConfig } from 'axios'
import { fmtDate } from '@/lib/format'
import { translate } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { usePlatformAuthStore } from '@/stores/platformAuth'

// Backend base URL. Defaults to the same-origin relative path "/api/v1" (served behind a
// reverse proxy, or Vite's dev proxy). Set VITE_API_BASE_URL to an absolute URL when the
// frontend and backend are deployed on different origins.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// Sessions ride on httpOnly cookies set by the backend — JS never sees the token.
// `withCredentials` makes cookies work on split-origin deployments too.
export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// Separate instance for the superadmin console: it rides the platform session cookie and
// never touches the tenant session, so the two consoles can be used independently.
export const platformApi = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

export function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

const SAFE_METHODS = new Set(['get', 'head', 'options'])

// Double-submit CSRF: echo the readable mc_csrf cookie in a header the browser would
// never add on its own. The backend rejects cookie-authenticated mutations without it.
function attachCsrf(config: InternalAxiosRequestConfig) {
  if (!SAFE_METHODS.has((config.method ?? 'get').toLowerCase())) {
    const csrf = readCookie('mc_csrf')
    if (csrf) config.headers['X-CSRF-Token'] = csrf
  }
  return config
}

api.interceptors.request.use(attachCsrf)
platformApi.interceptors.request.use(attachCsrf)

// On 401, clear the session (cookie expired or invalid) → router redirects to login.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && useAuthStore.getState().session) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  },
)

platformApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && usePlatformAuthStore.getState().session) {
      usePlatformAuthStore.getState().logout()
    }
    return Promise.reject(error)
  },
)

/** HTTP status code of an Axios error, or undefined for non-HTTP failures. */
export function errorStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined
}

/** Extract a human-readable message from an Axios error. */
// Params whose values are themselves codes get rendered through an existing label, so a
// message reads "No tienes permiso para esta acción: Enmendar expedientes" rather than
// "...: records.amend". Unknown values are shown as sent.
const PARAM_LABELS: Record<string, (value: string) => string> = {
  permission: (v) => `permission.${v.replace('.', '_')}`,
  permissions: (v) => `permission.${v.replace('.', '_')}`,
  current: (v) => `status.${v}`,
  attempted: (v) => `status.${v}`,
  entity: (v) => `audit.entity.${v}`,
  field: (v) => `vital.${v}`,
  role: (v) => `role.${v}`,
}

function label(key: string, raw: string): string {
  const toKey = PARAM_LABELS[key]
  if (!toKey) return raw
  // List params ("a, b") are labelled item by item.
  return raw
    .split(', ')
    .map((v) => {
      const k = toKey(v)
      const text = translate(k)
      return text === k ? v : text
    })
    .join(', ')
}

function interpolate(template: string, params: Record<string, unknown>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key]
    if (value === undefined || value === null) return match
    if (key === 'date') return fmtDate(String(value))
    return label(key, String(value))
  })
}

/**
 * User-facing text for a failed request. Error bodies carry a stable `code` (+ `params`)
 * that is translated here; the English `detail` is only for API clients and logs.
 * Codes without a translation (e.g. a generic `http.404`) use the caller's fallback.
 */
export function errorMessage(error: unknown, fallback?: string): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    const code = typeof data?.code === 'string' ? data.code : null
    if (code) {
      const key = `err.${code}`
      const template = translate(key)
      if (template !== key) return interpolate(template, data.params ?? {})
    }
  }
  return fallback ?? translate('app.error_generic')
}

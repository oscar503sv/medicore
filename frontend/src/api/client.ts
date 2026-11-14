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

// With Secure cookies the backend prefixes the names with __Host-; in plain-http dev they
// are unprefixed, so try both.
function readCsrf(base: string): string | null {
  return readCookie(`__Host-${base}`) ?? readCookie(base)
}

// CSRF: echo the readable CSRF cookie in a header the browser would never add on its own.
// The value is bound to the session server-side; mutations without it are rejected.
function csrfInterceptor(base: string) {
  return (config: InternalAxiosRequestConfig) => {
    if (!SAFE_METHODS.has((config.method ?? 'get').toLowerCase())) {
      const csrf = readCsrf(base)
      if (csrf) config.headers['X-CSRF-Token'] = csrf
    }
    return config
  }
}

api.interceptors.request.use(csrfInterceptor('mc_csrf'))
platformApi.interceptors.request.use(csrfInterceptor('mc_console_csrf'))

/** Marks a request as polling, so the console does not count it as user activity. */
export const BACKGROUND = { headers: { 'X-Background-Refresh': '1' } }

function isCsrfRejection(error: { response?: { status?: number; data?: { code?: string } } }) {
  return error.response?.status === 403 && error.response.data?.code === 'auth.csrf_invalid'
}

// On 401, clear the session (cookie expired or invalid) → router redirects to login.
// A rejected CSRF token means the session cookie was replaced or is gone: same treatment.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const expired = error.response?.status === 401 || isCsrfRejection(error)
    if (expired && useAuthStore.getState().session) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  },
)

platformApi.interceptors.response.use(
  (response) => response,
  (error) => {
    const store = usePlatformAuthStore.getState()
    if (store.session) {
      if (error.response?.status === 401) {
        store.expire(error.response.data?.code)
      } else if (isCsrfRejection(error)) {
        store.expire('auth.session_expired')
      }
    }
    return Promise.reject(error)
  },
)

/** HTTP status code of an Axios error, or undefined for non-HTTP failures. */
export function errorStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined
}

/** Backend error code (e.g. `auth.mfa_challenge_expired`) of an Axios error, if it has one. */
export function errorCode(error: unknown): string | undefined {
  if (!axios.isAxiosError(error)) return undefined
  const code = error.response?.data?.code
  return typeof code === 'string' ? code : undefined
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

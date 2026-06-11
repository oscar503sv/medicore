import axios, { type InternalAxiosRequestConfig } from 'axios'
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
export function errorMessage(error: unknown, fallback = 'Algo salió mal'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  }
  return fallback
}

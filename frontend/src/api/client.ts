import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { usePlatformAuthStore } from '@/stores/platformAuth'

// Backend base URL. Defaults to the same-origin relative path "/api/v1" (served behind a
// reverse proxy, or Vite's dev proxy). Set VITE_API_BASE_URL to an absolute URL when the
// frontend and backend are deployed on different origins.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Separate instance for the superadmin console: it carries the platform token and never
// touches the tenant session, so the two consoles can be used independently.
export const platformApi = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

platformApi.interceptors.request.use((config) => {
  const token = usePlatformAuthStore.getState().session?.token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

platformApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && usePlatformAuthStore.getState().session) {
      usePlatformAuthStore.getState().logout()
    }
    return Promise.reject(error)
  },
)

// Attach the bearer token to every request.
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().session?.token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401, clear the session (token expired or invalid) → router redirects to login.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && useAuthStore.getState().session) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  },
)

/** Extract a human-readable message from an Axios error. */
export function errorMessage(error: unknown, fallback = 'Algo salió mal'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  }
  return fallback
}

import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

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

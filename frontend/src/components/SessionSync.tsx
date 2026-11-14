import { useEffect } from 'react'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

/**
 * Refreshes the persisted session from the server once per signed-in user, so role,
 * permissions or a pending password change made elsewhere reach tabs that were already
 * logged in. Best-effort: a 401 already logs out through the interceptor.
 */
export function SessionSync() {
  const userId = useAuthStore((s) => s.session?.user_id)
  const syncProfile = useAuthStore((s) => s.syncProfile)

  useEffect(() => {
    if (!userId) return
    authApi
      .getMyProfile()
      .then((profile) => {
        if (useAuthStore.getState().session?.user_id === userId) syncProfile(profile)
      })
      .catch(() => {})
  }, [userId, syncProfile])

  return null
}

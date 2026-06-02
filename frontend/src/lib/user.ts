import type { Role, Sex } from '@/types'

/**
 * Name to greet the logged-in user with.
 *
 * Doctors are addressed by title + surname ("Dr. García" / "Dra. García"), where the title
 * comes from their sex and the surname is everything after the first given name. Everyone else
 * is greeted by their first name. Falls back gracefully when sex is unknown (defaults to "Dr.").
 */
export function greetingName(
  name: string,
  role?: Role | null,
  sex?: Sex | string | null,
): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return ''
  if (role === 'doctor') {
    const title = sex === 'female' ? 'Dra.' : 'Dr.'
    const surname = parts.length > 1 ? parts.slice(1).join(' ') : parts[0]
    return `${title} ${surname}`
  }
  return parts[0]
}

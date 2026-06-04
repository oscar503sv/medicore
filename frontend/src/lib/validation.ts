// Shared input validation/formatting helpers.

// Local phone format: 8 digits as XXXX-XXXX (e.g. 7777-8956).
export const PHONE_RE = /^\d{4}-\d{4}$/
// Unicode-friendly email so accented locals like "lucía.12@example.com" pass.
// (The native type="email" check is ASCII-only and rejects them, hence we validate here.)
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u

/** Format raw input into the XXXX-XXXX phone mask (caps at 8 digits). */
export function formatPhone(input: string): string {
  const digits = input.replace(/\D/g, '').slice(0, 8)
  return digits.length <= 4 ? digits : `${digits.slice(0, 4)}-${digits.slice(4)}`
}

/** True when a phone is empty (optional) or matches the XXXX-XXXX format. */
export function isValidPhone(phone: string): boolean {
  return !phone.trim() || PHONE_RE.test(phone.trim())
}

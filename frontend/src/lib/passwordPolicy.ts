// Client mirror of the backend password policy (domain/services/password_policy.py), used to
// guide people while they type. The server stays the authority: it also rejects common
// passwords, which the client doesn't try to list.

export const PASSWORD_MIN = 10
const MAX_BYTES = 72
const MIN_PERSONAL = 4

export type PasswordRule = 'length' | 'mix' | 'personal'

function normalize(text: string): string {
  return text.toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '')
}

function personalWords(personal: (string | null | undefined)[]): string[] {
  return personal
    .filter((p): p is string => !!p)
    .flatMap((p) =>
      normalize(p)
        .split('@')[0]
        .split(/[\s.\-_+]+/),
    )
    .filter((w) => w.length >= MIN_PERSONAL)
}

/** Each rule and whether the password meets it. */
export function checkPassword(
  password: string,
  personal: (string | null | undefined)[] = [],
): Record<PasswordRule, boolean> {
  const bytes = new TextEncoder().encode(password).length
  const hasLetter = /\p{L}/u.test(password)
  const hasOther = /[^\p{L}\s]/u.test(password)
  const normalized = normalize(password)
  return {
    length: password.length >= PASSWORD_MIN && bytes <= MAX_BYTES,
    mix: hasLetter && hasOther && new Set(password).size >= 4,
    personal: !personalWords(personal).some((w) => normalized.includes(w)),
  }
}

export function meetsPolicy(password: string, personal: (string | null | undefined)[] = []) {
  return Object.values(checkPassword(password, personal)).every(Boolean)
}

/** A readable temporary password that always meets the policy, e.g. "Kp7m-Rt4x-Wq9z". */
export function genPassword(): string {
  const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz'
  const digits = '23456789'
  const pick = (set: string) => set[crypto.getRandomValues(new Uint32Array(1))[0] % set.length]
  const group = () => pick(letters) + pick(letters) + pick(digits) + pick(letters)
  return [group(), group(), group()].join('-')
}

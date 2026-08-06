const SESSION_KEY = 'crawler.auth.session'

export interface AuthUser {
  id: number
  username: string
  avatarBase64: string | null
  role: 'admin' | 'user'
  isActive: boolean
}

export interface AuthSession {
  accessToken: string
  expiresAt: string
  user: AuthUser
}

export function saveSession(session: AuthSession) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function loadSession(): AuthSession | null {
  const raw = localStorage.getItem(SESSION_KEY)
  if (!raw) return null

  try {
    const value: unknown = JSON.parse(raw)
    if (!isAuthSession(value)) throw new Error('invalid session')
    return value
  } catch {
    localStorage.removeItem(SESSION_KEY)
    return null
  }
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY)
}

function isAuthSession(value: unknown): value is AuthSession {
  if (typeof value !== 'object' || value === null) return false
  const session = value as Partial<AuthSession>
  const user = session.user as Partial<AuthUser> | undefined
  return (
    typeof session.accessToken === 'string' &&
    session.accessToken.length > 0 &&
    typeof session.expiresAt === 'string' &&
    typeof user === 'object' &&
    user !== null &&
    typeof user.id === 'number' &&
    typeof user.username === 'string' &&
    (user.avatarBase64 === null || typeof user.avatarBase64 === 'string') &&
    (user.role === 'admin' || user.role === 'user') &&
    typeof user.isActive === 'boolean'
  )
}

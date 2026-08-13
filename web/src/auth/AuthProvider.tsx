import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import { ApiClient } from '../api/client'
import { clearSession, loadSession, saveSession } from './session'
import type { AuthSession } from './session'

interface ApiAuthSession {
  access_token: string
  expires_at: string
  user: {
    id: number
    username: string
    avatar_base64: string | null
    role: 'admin' | 'user'
    is_active: boolean
  }
}

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated'

interface AuthContextValue {
  status: AuthStatus
  session: AuthSession | null
  client: ApiClient
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  updateAvatar: (avatarBase64: string | null) => Promise<void>
  updatePassword: (currentPassword: string, newPassword: string) => Promise<void>
}

type ClientFactory = (
  getToken: () => string | null,
  onUnauthorized: () => void | Promise<void>,
) => ApiClient

interface AuthProviderProps extends PropsWithChildren {
  clientFactory?: ClientFactory
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children, clientFactory = defaultClientFactory }: AuthProviderProps) {
  const initialSessionRef = useRef(loadSession())
  const [session, setSession] = useState<AuthSession | null>(initialSessionRef.current)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const sessionRef = useRef<AuthSession | null>(initialSessionRef.current)
  const validationRequestRef = useRef<Promise<ApiAuthSession> | null>(null)

  const resetSession = useCallback(() => {
    clearSession()
    sessionRef.current = null
    setSession(null)
    setStatus('anonymous')
  }, [])

  const client = useMemo(
    () => clientFactory(() => sessionRef.current?.accessToken ?? null, resetSession),
    [clientFactory, resetSession],
  )

  const applySession = useCallback((raw: ApiAuthSession, avatarFallback?: string | null) => {
    const next = mapSession(raw, avatarFallback)
    saveSession(next)
    sessionRef.current = next
    setSession(next)
    setStatus('authenticated')
  }, [])

  useEffect(() => {
    const stored = initialSessionRef.current
    if (!stored) {
      setStatus('anonymous')
      return
    }
    let active = true
    validationRequestRef.current ??= client.get<ApiAuthSession>('/v1/auth/me?include_avatar=false')
    validationRequestRef.current
      .then((raw) => {
        if (active) applySession(raw, stored.user.avatarBase64)
      })
      .catch(() => {
        if (active) resetSession()
      })
    return () => {
      active = false
    }
  }, [applySession, client, resetSession])

  const login = useCallback(
    async (username: string, password: string) => {
      const raw = await client.post<ApiAuthSession>('/v1/auth/login', {
        username,
        password,
      })
      applySession(raw)
    },
    [applySession, client],
  )

  const logout = useCallback(async () => {
    try {
      await client.post<{ message: string }>('/v1/auth/logout')
    } catch {
      // A local logout must remain available while the backend is unavailable.
    } finally {
      resetSession()
    }
  }, [client, resetSession])

  const updateAvatar = useCallback(
    async (avatarBase64: string | null) => {
      const raw = await client.patch<ApiAuthSession>('/v1/auth/me/avatar', {
        avatar_base64: avatarBase64,
      })
      applySession(raw)
    },
    [applySession, client],
  )

  const updatePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await client.patch<{ message: string }>('/v1/auth/me/password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      resetSession()
    },
    [client, resetSession],
  )

  const value = useMemo(
    () => ({ status, session, client, login, logout, updateAvatar, updatePassword }),
    [client, login, logout, session, status, updateAvatar, updatePassword],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

function defaultClientFactory(getToken: () => string | null, onUnauthorized: () => void | Promise<void>) {
  return new ApiClient({ getToken, onUnauthorized })
}

function mapSession(raw: ApiAuthSession, avatarFallback?: string | null): AuthSession {
  return {
    accessToken: raw.access_token,
    expiresAt: raw.expires_at,
    user: {
      id: raw.user.id,
      username: raw.user.username,
      avatarBase64: avatarFallback === undefined ? raw.user.avatar_base64 : avatarFallback,
      role: raw.user.role,
      isActive: raw.user.is_active,
    },
  }
}

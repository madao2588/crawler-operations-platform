import { clearSession, loadSession, saveSession } from './session'

const session = {
  accessToken: 'token-123',
  expiresAt: '2026-08-04T00:00:00Z',
  user: {
    id: 7,
    username: 'admin',
    avatarBase64: null,
    role: 'admin' as const,
    isActive: true,
  },
}

describe('session storage', () => {
  it('persists and restores the complete authenticated session', () => {
    saveSession(session)
    expect(loadSession()).toEqual(session)
  })

  it('clears malformed data instead of exposing a partial session', () => {
    localStorage.setItem('crawler.auth.session', '{not-json')
    expect(loadSession()).toBeNull()
    expect(localStorage.getItem('crawler.auth.session')).toBeNull()
  })

  it('rejects a legacy session without a verified role', () => {
    localStorage.setItem('crawler.auth.session', JSON.stringify({
      accessToken: 'legacy-token',
      expiresAt: '2026-08-04T00:00:00Z',
      user: { id: 1, username: 'legacy', avatarBase64: null },
    }))
    expect(loadSession()).toBeNull()
  })

  it('removes the stored session on logout', () => {
    saveSession(session)
    clearSession()
    expect(loadSession()).toBeNull()
  })
})

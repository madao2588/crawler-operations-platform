import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiClient } from '../api/client'
import { AuthProvider, useAuth } from './AuthProvider'
import { saveSession } from './session'

function Probe() {
  const auth = useAuth()
  return <div>{auth.status === 'authenticated' ? auth.session?.user.username : auth.status}</div>
}

function AvatarProbe() {
  const auth = useAuth()
  return (
    <div>
      <span>{auth.session?.user.avatarBase64 ?? 'default'}</span>
      <button type="button" onClick={() => void auth.updateAvatar('iVBORw==')}>更新头像</button>
    </div>
  )
}

function PasswordProbe() {
  const auth = useAuth()
  return <button type="button" onClick={() => void auth.updatePassword('old-password', 'new-password-123')}>修改密码</button>
}

describe('AuthProvider', () => {
  it('validates a stored token with /v1/auth/me before exposing the app', async () => {
    saveSession({
      accessToken: 'stored-token',
      expiresAt: '2026-08-04T00:00:00Z',
      user: { id: 1, username: 'old-name', avatarBase64: null, role: 'admin', isActive: true },
    })
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 0,
          message: 'success',
          data: {
            access_token: 'stored-token',
            expires_at: '2026-08-04T00:00:00Z',
            user: { id: 1, username: '运营管理员', avatar_base64: null, role: 'admin', is_active: true },
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    render(
      <AuthProvider clientFactory={(getToken, onUnauthorized) => new ApiClient({ fetcher, getToken, onUnauthorized })}>
        <Probe />
      </AuthProvider>,
    )

    expect(screen.getByText('loading')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('运营管理员')).toBeInTheDocument())
    expect(fetcher).toHaveBeenCalledWith(
      '/v1/auth/me',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer stored-token' }),
      }),
    )
  })

  it('clears an invalid stored session and exposes the login state', async () => {
    saveSession({
      accessToken: 'expired-token',
      expiresAt: '2026-08-01T00:00:00Z',
      user: { id: 1, username: 'admin', avatarBase64: null, role: 'admin', isActive: true },
    })
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({ code: 401, message: 'session expired', data: null }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    render(
      <AuthProvider clientFactory={(getToken, onUnauthorized) => new ApiClient({ fetcher, getToken, onUnauthorized })}>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('anonymous')).toBeInTheDocument())
    expect(localStorage.getItem('crawler.auth.session')).toBeNull()
  })

  it('updates the account avatar and refreshes the stored session', async () => {
    saveSession({
      accessToken: 'stored-token',
      expiresAt: '2026-08-04T00:00:00Z',
      user: { id: 1, username: 'admin', avatarBase64: null, role: 'admin', isActive: true },
    })
    const sessionResponse = (avatar: string | null) =>
      new Response(
        JSON.stringify({
          code: 0,
          message: 'success',
          data: {
            access_token: 'stored-token',
            expires_at: '2026-08-04T00:00:00Z',
            user: { id: 1, username: 'admin', avatar_base64: avatar, role: 'admin', is_active: true },
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse(null))
      .mockResolvedValueOnce(sessionResponse('iVBORw=='))
    const user = userEvent.setup()

    render(
      <AuthProvider clientFactory={(getToken, onUnauthorized) => new ApiClient({ fetcher, getToken, onUnauthorized })}>
        <AvatarProbe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('default')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '更新头像' }))

    await waitFor(() => expect(screen.getByText('iVBORw==')).toBeInTheDocument())
    expect(fetcher).toHaveBeenLastCalledWith(
      '/v1/auth/me/avatar',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ avatar_base64: 'iVBORw==' }),
      }),
    )
    expect(localStorage.getItem('crawler.auth.session')).toContain('iVBORw==')
  })

  it('changes the password and clears the current session', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({ code: 0, message: 'success', data: { message: '密码已修改，请重新登录' } }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const user = userEvent.setup()

    render(
      <AuthProvider clientFactory={(getToken, onUnauthorized) => new ApiClient({ fetcher, getToken, onUnauthorized })}>
        <PasswordProbe />
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: '修改密码' }))
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      '/v1/auth/me/password',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ current_password: 'old-password', new_password: 'new-password-123' }),
      }),
    ))
    expect(localStorage.getItem('crawler.auth.session')).toBeNull()
  })
})

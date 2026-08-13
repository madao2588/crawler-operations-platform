import { ApiClient } from './client'

describe('ApiClient', () => {
  it('keeps the native browser fetch bound to window', async () => {
    const originalFetch = window.fetch
    const browserFetch = vi.fn(function (this: unknown) {
      if (this !== window) {
        throw new TypeError("Failed to execute 'fetch' on 'Window': Illegal invocation")
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({ code: 0, message: 'success', data: { status: 'ok' } }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    }) as unknown as typeof fetch
    window.fetch = browserFetch

    try {
      const client = new ApiClient()
      await expect(client.get<{ status: string }>('/health')).resolves.toEqual({
        status: 'ok',
      })
    } finally {
      window.fetch = originalFetch
    }

    expect(browserFetch).toHaveBeenCalledOnce()
  })

  it('unwraps the shared API response and attaches the bearer token', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({ code: 0, message: 'success', data: { status: 'ok' } }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const client = new ApiClient({
      fetcher,
      getToken: () => 'unit-token',
    })

    await expect(client.get<{ status: string }>('/health')).resolves.toEqual({
      status: 'ok',
    })
    expect(fetcher).toHaveBeenCalledWith(
      '/health',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer unit-token' }),
      }),
    )
  })

  it('reports the server message and notifies once when an authenticated request returns 401', async () => {
    const onUnauthorized = vi.fn()
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({ code: 401, message: 'session expired', data: null }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const client = new ApiClient({
      fetcher,
      getToken: () => 'expired-token',
      onUnauthorized,
    })

    await expect(client.get('/v1/notices')).rejects.toEqual(
      expect.objectContaining({
        message: 'session expired',
        status: 401,
      }),
    )
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('does not trigger global unauthorized handling for the login endpoint', async () => {
    const onUnauthorized = vi.fn()
    const client = new ApiClient({
      fetcher: vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({ code: 401, message: '用户名或密码错误', data: null }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
      getToken: () => null,
      onUnauthorized,
    })

    await expect(
      client.post('/v1/auth/login', { username: 'admin', password: 'bad' }),
    ).rejects.toMatchObject({ message: '用户名或密码错误' })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('coalesces concurrent 401 responses for the same expired token', async () => {
    const onUnauthorized = vi.fn()
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () =>
      new Response(
        JSON.stringify({ code: 401, message: 'session expired', data: null }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const client = new ApiClient({ fetcher, getToken: () => 'same-expired-token', onUnauthorized })

    await Promise.allSettled([client.get('/v1/notices'), client.get('/v1/dashboard/overview')])
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('identifies the failed request when the backend cannot be reached', async () => {
    const client = new ApiClient({
      fetcher: vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')),
    })

    await expect(client.get('/v1/dashboard/overview')).rejects.toMatchObject({
      message:
        '无法连接后端（GET /v1/dashboard/overview）：服务未响应。请确认 npm start 正在运行后重试。',
    })
  })
})

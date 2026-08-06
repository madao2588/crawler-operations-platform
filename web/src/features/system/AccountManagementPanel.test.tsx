import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiClient } from '../../api/client'
import { AccountManagementPanel } from './AccountManagementPanel'

describe('AccountManagementPanel', () => {
  it('lists accounts and creates a regular user', async () => {
    let users = [createUser({ id: 1, username: 'admin', role: 'admin' })]
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/auth/users' && (!init || init.method === 'GET')) {
        return jsonResponse(users)
      }
      if (url === '/v1/auth/users' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        const created = createUser({ id: 2, username: body.username, role: body.role })
        users = [...users, created]
        return jsonResponse(created)
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })
    const user = userEvent.setup()

    render(<AccountManagementPanel client={new ApiClient({ fetcher })} currentUserId={1} />)

    expect(await screen.findByText('admin')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '新建账号' }))
    const dialog = screen.getByRole('dialog', { name: '新建账号' })
    await user.type(within(dialog).getByLabelText('用户名'), 'researcher')
    await user.type(within(dialog).getByLabelText('初始密码'), '12345678')
    await user.click(within(dialog).getByRole('button', { name: '创建账号' }))

    await waitFor(() => expect(screen.getByText('researcher')).toBeInTheDocument())
    expect(fetcher).toHaveBeenCalledWith(
      '/v1/auth/users',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'researcher', password: '12345678', role: 'user' }),
      }),
    )
  })
})

function createUser(overrides: Record<string, unknown>) {
  return {
    id: 1,
    username: 'user',
    avatar_base64: null,
    role: 'user',
    is_active: true,
    created_at: '2026-08-05T09:00:00Z',
    ...overrides,
  }
}

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify({ code: 0, message: 'ok', data }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

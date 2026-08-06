import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const state = vi.hoisted(() => ({
  auth: {
    status: 'authenticated' as 'loading' | 'anonymous' | 'authenticated',
    session: { accessToken: 'token', expiresAt: 'later', user: { id: 1, username: 'admin', avatarBase64: null, role: 'admin', isActive: true } },
    login: vi.fn(),
    logout: vi.fn(),
    updateAvatar: vi.fn(),
    updatePassword: vi.fn(),
    client: {},
  },
}))

vi.mock('./auth/AuthProvider', () => ({ useAuth: () => state.auth }))
vi.mock('./features/dashboard', () => ({ DashboardPage: () => <h2>看板模块</h2> }))
vi.mock('./features/notices', () => ({ NoticesPage: () => <h2>公告模块</h2> }))
vi.mock('./features/keywords/KeywordRulesPage', () => ({ KeywordRulesPage: () => <h2>规则模块</h2> }))
vi.mock('./features/sources/SourceSitesPage', () => ({ SourceSitesPage: () => <h2>来源模块</h2> }))
vi.mock('./features/system/SystemManagementPage', () => ({ SystemManagementPage: () => <h2>系统模块</h2> }))

import { App } from './App'

describe('App', () => {
  it('renders deep links and switches business routes from the shell', async () => {
    window.history.replaceState(null, '', '/notices?high_priority=true')
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByRole('heading', { name: '公告模块' })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: '系统管理' }))
    expect(await screen.findByRole('heading', { name: '系统模块' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/system')
  })

  it('keeps the requested URL while an anonymous user logs in', () => {
    state.auth.status = 'anonymous'
    state.auth.session = null as never
    window.history.replaceState(null, '', '/sources')
    render(<App />)

    expect(screen.getByRole('heading', { name: '新药部情报监测平台' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/sources')
  })
})

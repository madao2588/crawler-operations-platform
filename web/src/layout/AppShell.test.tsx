import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('marks the current navigation item and navigates with semantic links', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    render(
      <AppShell path="/notices" username="admin" onNavigate={onNavigate} onLogout={vi.fn()} onAvatarChange={vi.fn()}>
        <h1>公告内容</h1>
      </AppShell>,
    )

    expect(screen.getByRole('link', { name: '公告中心' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('main')).toHaveAttribute('data-scroll-root', 'viewport')
    await user.click(screen.getByRole('link', { name: '关键词规则' }))
    expect(onNavigate).toHaveBeenCalledWith('/keywords')
  })

  it('keeps logout separate from primary navigation', async () => {
    const onLogout = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AppShell path="/" username="运营管理员" onNavigate={vi.fn()} onLogout={onLogout} onAvatarChange={vi.fn()}>
        <div>看板</div>
      </AppShell>,
    )

    await user.click(screen.getByRole('button', { name: '退出登录' }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })

  it('opens and dismisses the compact navigation with the keyboard', async () => {
    const user = userEvent.setup()
    render(
      <AppShell path="/" username="运营管理员" onNavigate={vi.fn()} onLogout={vi.fn()} onAvatarChange={vi.fn()}>
        <div>看板</div>
      </AppShell>,
    )

    const trigger = screen.getByRole('button', { name: '打开导航' })
    await user.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    await user.keyboard('{Escape}')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

  it('previews and saves an uploaded account avatar', async () => {
    const onAvatarChange = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AppShell
        path="/notices"
        username="admin"
        onNavigate={vi.fn()}
        onLogout={vi.fn()}
        onAvatarChange={onAvatarChange}
      >
        <div>公告</div>
      </AppShell>,
    )

    await user.click(screen.getByRole('button', { name: '账号设置' }))
    expect(screen.getByRole('dialog', { name: '账号设置' })).toBeInTheDocument()

    const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'avatar.png', {
      type: 'image/png',
    })
    await user.upload(screen.getByLabelText('选择头像图片'), file)
    await user.click(screen.getByRole('button', { name: '保存头像' }))

    await waitFor(() => expect(onAvatarChange).toHaveBeenCalledWith('iVBORw=='))
    expect(screen.queryByRole('dialog', { name: '账号设置' })).not.toBeInTheDocument()
  })

  it('restores the default account avatar after confirmation', async () => {
    const onAvatarChange = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AppShell
        path="/"
        username="admin"
        avatarBase64="iVBORw=="
        onNavigate={vi.fn()}
        onLogout={vi.fn()}
        onAvatarChange={onAvatarChange}
      >
        <div>看板</div>
      </AppShell>,
    )

    await user.click(screen.getByRole('button', { name: '账号设置' }))
    await user.click(screen.getByRole('button', { name: '恢复默认头像' }))
    await user.click(screen.getByRole('button', { name: '保存头像' }))

    await waitFor(() => expect(onAvatarChange).toHaveBeenCalledWith(null))
  })

  it('shows the account role and allows changing the current password', async () => {
    const onPasswordChange = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AppShell
        path="/"
        username="reader"
        role="user"
        onNavigate={vi.fn()}
        onLogout={vi.fn()}
        onAvatarChange={vi.fn()}
        onPasswordChange={onPasswordChange}
      >
        <div>看板</div>
      </AppShell>,
    )

    expect(screen.getByText('普通用户')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '账号设置' }))
    await user.type(screen.getByLabelText('当前密码'), 'old-password')
    await user.type(screen.getByLabelText('新密码'), 'new-password-123')
    await user.type(screen.getByLabelText('确认新密码'), 'new-password-123')
    await user.click(screen.getByRole('button', { name: '修改密码' }))

    await waitFor(() => expect(onPasswordChange).toHaveBeenCalledWith('old-password', 'new-password-123'))
  })
})

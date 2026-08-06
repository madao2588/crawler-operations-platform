import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginPage } from './LoginPage'

describe('LoginPage', () => {
  it('submits labeled credentials once and shows progress', async () => {
    const onLogin = vi.fn(() => new Promise<void>(() => undefined))
    const user = userEvent.setup()
    render(<LoginPage onLogin={onLogin} />)

    await user.type(screen.getByLabelText('用户名'), 'admin')
    await user.type(screen.getByLabelText('密码'), 'secret')
    await user.click(screen.getByRole('button', { name: '登录系统' }))

    expect(onLogin).toHaveBeenCalledWith('admin', 'secret')
    expect(screen.getByRole('button', { name: '正在登录' })).toBeDisabled()
  })

  it('shows a recoverable inline error', async () => {
    const user = userEvent.setup()
    render(<LoginPage onLogin={() => Promise.reject(new Error('用户名或密码错误'))} />)

    await user.type(screen.getByLabelText('用户名'), 'admin')
    await user.type(screen.getByLabelText('密码'), 'wrong')
    await user.click(screen.getByRole('button', { name: '登录系统' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('用户名或密码错误')
    expect(screen.getByRole('button', { name: '登录系统' })).toBeEnabled()
  })

  it('lets the user reveal and hide the password without clearing it', async () => {
    const user = userEvent.setup()
    render(<LoginPage onLogin={vi.fn()} />)

    const password = screen.getByLabelText('密码')
    await user.type(password, 'secret')

    expect(password).toHaveAttribute('type', 'password')
    await user.click(screen.getByRole('button', { name: '显示密码' }))
    expect(password).toHaveAttribute('type', 'text')
    expect(password).toHaveValue('secret')

    await user.click(screen.getByRole('button', { name: '隐藏密码' }))
    expect(password).toHaveAttribute('type', 'password')
  })
})

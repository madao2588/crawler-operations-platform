import { Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'

interface LoginPageProps {
  onLogin: (username: string, password: string) => Promise<void>
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [passwordVisible, setPasswordVisible] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError('')
    try {
      await onLogin(username.trim(), password)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '登录失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-brand-row">
          <div className="brand-mark" aria-hidden="true">AI</div>
          <span><strong>新药情报工作台</strong><small>安全的本地监测环境</small></span>
        </div>
        <p className="eyebrow">NEW DRUG INTELLIGENCE</p>
        <h1 id="login-title">新药部情报监测平台</h1>
        <p className="login-intro">集中查看项目申报、结果公示、行业会议与竞品研发动态。</p>
        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="username">用户名</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <label htmlFor="password">密码</label>
          <div className="password-field">
            <input
              id="password"
              name="password"
              type={passwordVisible ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button
              className="password-toggle"
              type="button"
              aria-label={passwordVisible ? '隐藏密码' : '显示密码'}
              aria-pressed={passwordVisible}
              onClick={() => setPasswordVisible((visible) => !visible)}
            >
              {passwordVisible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </button>
          </div>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={submitting || !username.trim() || !password}>
            {submitting ? '正在登录' : '登录系统'}
          </button>
        </form>
        <p className="login-help"><ShieldCheck aria-hidden="true" />账号由系统管理员在本机环境变量中配置</p>
      </section>
    </main>
  )
}

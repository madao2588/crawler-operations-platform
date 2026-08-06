import { KeyRound, LoaderCircle, Plus, UserRoundCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { ApiClient } from '../../api/client'
import { ApiError } from '../../api/client'
import { DetailDrawer } from '../../components/UiPrimitives'

interface ManagedUser {
  id: number
  username: string
  avatar_base64: string | null
  role: 'admin' | 'user'
  is_active: boolean
  created_at: string
}

export function AccountManagementPanel({
  client,
  currentUserId,
}: {
  client: ApiClient
  currentUserId: number
}) {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [resetUser, setResetUser] = useState<ManagedUser | null>(null)
  const [busyIds, setBusyIds] = useState<number[]>([])

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setUsers(await client.get<ManagedUser[]>('/v1/auth/users'))
    } catch (reason) {
      setError(toMessage(reason))
    } finally {
      setLoading(false)
    }
  }, [client])

  useEffect(() => {
    void loadUsers()
  }, [loadUsers])

  async function updateStatus(user: ManagedUser) {
    if (busyIds.includes(user.id) || user.id === currentUserId) return
    setBusyIds((current) => [...current, user.id])
    setFeedback('')
    try {
      const updated = await client.patch<ManagedUser>(`/v1/auth/users/${user.id}/status`, {
        is_active: !user.is_active,
      })
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setFeedback(updated.is_active ? `已启用 ${updated.username}` : `已停用 ${updated.username}`)
    } catch (reason) {
      setFeedback(toMessage(reason))
    } finally {
      setBusyIds((current) => current.filter((id) => id !== user.id))
    }
  }

  return (
    <section className="panel account-management-panel">
      <div className="panel-header">
        <div>
          <h2>账号管理</h2>
          <p className="panel-meta">内部账号由管理员统一创建；停用后会立即退出登录。</p>
        </div>
        <button className="secondary-action" type="button" onClick={() => setCreateOpen(true)}>
          <Plus aria-hidden="true" />
          新建账号
        </button>
      </div>

      {feedback ? <p className="system-feedback system-feedback--success" role="status">{feedback}</p> : null}
      {loading ? <p className="panel-message">账号加载中…</p> : null}
      {error ? (
        <div className="panel-error" role="alert">
          <p>{error}</p>
          <button className="ghost-action" type="button" onClick={() => void loadUsers()}>重试</button>
        </div>
      ) : null}
      {!loading && !error ? (
        <div className="table-shell" role="region" aria-label="账号列表" data-scroll-region="table" tabIndex={0}>
          <table className="data-table account-table">
            <thead>
              <tr>
                <th>账号</th>
                <th>角色</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => {
                const isCurrent = user.id === currentUserId
                const busy = busyIds.includes(user.id)
                return (
                  <tr key={user.id}>
                    <td>
                      <strong>{user.username}</strong>
                      {isCurrent ? <span className="account-current-badge">当前账号</span> : null}
                    </td>
                    <td><span className={user.role === 'admin' ? 'status-badge is-info' : 'status-badge'}>{user.role === 'admin' ? '管理员' : '普通用户'}</span></td>
                    <td><span className={user.is_active ? 'status-badge is-success' : 'status-badge'}>{user.is_active ? '正常' : '已停用'}</span></td>
                    <td>{formatDateTime(user.created_at)}</td>
                    <td>
                      <div className="row-actions">
                        <button className="ghost-action" type="button" onClick={() => setResetUser(user)}>
                          <KeyRound aria-hidden="true" />
                          重置密码
                        </button>
                        <button
                          className={user.is_active ? 'ghost-action is-danger' : 'ghost-action'}
                          type="button"
                          disabled={isCurrent || busy}
                          title={isCurrent ? '不能停用当前登录账号' : undefined}
                          onClick={() => void updateStatus(user)}
                        >
                          {busy ? '处理中' : user.is_active ? '停用' : '启用'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <CreateAccountDrawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={async (payload) => {
          const created = await client.post<ManagedUser>('/v1/auth/users', payload)
          setUsers((current) => [...current, created])
          setCreateOpen(false)
          setFeedback(`账号 ${created.username} 已创建`)
        }}
      />
      <ResetPasswordDrawer
        user={resetUser}
        onClose={() => setResetUser(null)}
        onReset={async (password) => {
          if (!resetUser) return
          await client.post<{ message: string }>(`/v1/auth/users/${resetUser.id}/reset-password`, {
            new_password: password,
          })
          setFeedback(`${resetUser.username} 的密码已重置`)
          setResetUser(null)
        }}
      />
    </section>
  )
}

function CreateAccountDrawer({
  open,
  onClose,
  onCreate,
}: {
  open: boolean
  onClose: () => void
  onCreate: (payload: { username: string; password: string; role: 'admin' | 'user' }) => Promise<void>
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'admin' | 'user'>('user')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setUsername('')
    setPassword('')
    setRole('user')
    setError('')
  }, [open])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    try {
      await onCreate({ username: username.trim(), password, role })
    } catch (reason) {
      setError(toMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <DetailDrawer open={open} title="新建账号" description="建议每个人使用独立账号，便于停用和重置密码。" width="compact" onClose={() => { if (!saving) onClose() }}>
      <form className="account-form" onSubmit={(event) => void submit(event)}>
        <label><span>用户名</span><input required minLength={2} value={username} onChange={(event) => setUsername(event.target.value)} autoFocus /></label>
        <label><span>初始密码</span><input required minLength={6} type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <label><span>角色</span><select value={role} onChange={(event) => setRole(event.target.value as 'admin' | 'user')}><option value="user">普通用户</option><option value="admin">管理员</option></select></label>
        <p className="account-form__hint">普通用户可查看、筛选和导出；管理员还可修改配置和运行采集。</p>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button className="ghost-action" type="button" disabled={saving} onClick={onClose}>取消</button>
          <button className="primary-action" type="submit" disabled={saving || username.trim().length < 2 || password.length < 6}>
            {saving ? <LoaderCircle className="spin-icon" aria-hidden="true" /> : <UserRoundCheck aria-hidden="true" />}
            {saving ? '创建中' : '创建账号'}
          </button>
        </div>
      </form>
    </DetailDrawer>
  )
}

function ResetPasswordDrawer({
  user,
  onClose,
  onReset,
}: {
  user: ManagedUser | null
  onClose: () => void
  onReset: (password: string) => Promise<void>
}) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    setPassword('')
    setConfirmPassword('')
    setError('')
  }, [user])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致。')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onReset(password)
    } catch (reason) {
      setError(toMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <DetailDrawer open={Boolean(user)} title="重置密码" description={user ? `为 ${user.username} 设置新密码；该账号现有登录会立即失效。` : undefined} width="compact" onClose={() => { if (!saving) onClose() }}>
      <form className="account-form" onSubmit={(event) => void submit(event)}>
        <label><span>新密码</span><input required minLength={6} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoFocus /></label>
        <label><span>确认新密码</span><input required minLength={6} type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button className="ghost-action" type="button" disabled={saving} onClick={onClose}>取消</button>
          <button className="primary-action" type="submit" disabled={saving || password.length < 6 || confirmPassword.length < 6}>{saving ? '重置中' : '确认重置'}</button>
        </div>
      </form>
    </DetailDrawer>
  )
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}

function toMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}

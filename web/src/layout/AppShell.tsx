import {
  Camera,
  FileText,
  Globe2,
  ImagePlus,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  KeyRound,
  RotateCcw,
  Settings2,
  Tags,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, ComponentType, MouseEvent, PropsWithChildren } from 'react'
import type { AppPath } from '../app/router'
import { DetailDrawer } from '../components/UiPrimitives'

type ShellPath = Exclude<AppPath, '/login'>

interface AppShellProps extends PropsWithChildren {
  path: ShellPath
  username: string
  avatarBase64?: string | null
  role?: 'admin' | 'user'
  onNavigate: (to: ShellPath) => void
  onLogout: () => void | Promise<void>
  onAvatarChange: (avatarBase64: string | null) => Promise<void>
  onPasswordChange?: (currentPassword: string, newPassword: string) => Promise<void>
}

const MAX_AVATAR_BYTES = 2 * 1024 * 1024
const SUPPORTED_AVATAR_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

const navigation: Array<{ path: ShellPath; label: string; icon: ComponentType<{ 'aria-hidden'?: boolean }> }> = [
  { path: '/', label: '首页看板', icon: LayoutDashboard },
  { path: '/notices', label: '公告中心', icon: FileText },
  { path: '/keywords', label: '关键词规则', icon: Tags },
  { path: '/sources', label: '来源站点', icon: Globe2 },
  { path: '/system', label: '系统管理', icon: Settings2 },
]

const subtitles: Record<ShellPath, string> = {
  '/': '关键情报、项目线索与系统运行状态总览',
  '/notices': '按来源、类别和业务优先级筛选采集结果',
  '/keywords': '维护命中规则与高优先级情报触发条件',
  '/sources': '管理采集站点、任务模板与单篇文章登记',
  '/system': '统一管理采集任务、运行日志与系统配置',
}

export function AppShell({
  path,
  username,
  avatarBase64,
  role = 'admin',
  onNavigate,
  onLogout,
  onAvatarChange,
  onPasswordChange,
  children,
}: AppShellProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [avatarEditorOpen, setAvatarEditorOpen] = useState(false)
  const [draftAvatar, setDraftAvatar] = useState<string | null>(avatarBase64 ?? null)
  const [avatarError, setAvatarError] = useState('')
  const [avatarSaving, setAvatarSaving] = useState(false)
  const [avatarFeedback, setAvatarFeedback] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [passwordSaving, setPasswordSaving] = useState(false)
  const feedbackTimerRef = useRef<number | null>(null)
  const current = navigation.find((item) => item.path === path) ?? navigation[0]

  useEffect(() => {
    if (!menuOpen) return undefined
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [menuOpen])

  useEffect(() => () => {
    if (feedbackTimerRef.current !== null) window.clearTimeout(feedbackTimerRef.current)
  }, [])

  function handleLink(event: MouseEvent<HTMLAnchorElement>, to: ShellPath) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    setMenuOpen(false)
    onNavigate(to)
  }

  function openAvatarEditor() {
    setDraftAvatar(avatarBase64 ?? null)
    setAvatarError('')
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordError('')
    setAvatarEditorOpen(true)
  }

  function handleAvatarFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!SUPPORTED_AVATAR_TYPES.has(file.type)) {
      setAvatarError('仅支持 PNG、JPG 或 WebP 图片。')
      return
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setAvatarError('头像图片不能超过 2MB。')
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : ''
      const encoded = result.includes(',') ? result.slice(result.indexOf(',') + 1) : ''
      if (!encoded) {
        setAvatarError('无法读取这张图片，请重新选择。')
        return
      }
      setDraftAvatar(encoded)
      setAvatarError('')
    }
    reader.onerror = () => setAvatarError('无法读取这张图片，请重新选择。')
    reader.readAsDataURL(file)
  }

  async function saveAvatar() {
    setAvatarSaving(true)
    setAvatarError('')
    try {
      await onAvatarChange(draftAvatar)
      setAvatarEditorOpen(false)
      setAvatarFeedback(draftAvatar ? '头像已保存' : '已恢复默认头像')
      if (feedbackTimerRef.current !== null) window.clearTimeout(feedbackTimerRef.current)
      feedbackTimerRef.current = window.setTimeout(() => setAvatarFeedback(''), 2400)
    } catch (error) {
      setAvatarError(error instanceof Error ? error.message : '头像保存失败，请重试。')
    } finally {
      setAvatarSaving(false)
    }
  }

  async function savePassword() {
    if (!onPasswordChange || passwordSaving) return
    if (newPassword.length < 6) {
      setPasswordError('新密码至少需要 6 个字符。')
      return
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('两次输入的新密码不一致。')
      return
    }
    setPasswordSaving(true)
    setPasswordError('')
    try {
      await onPasswordChange(currentPassword, newPassword)
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : '密码修改失败，请重试。')
    } finally {
      setPasswordSaving(false)
    }
  }

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside id="primary-navigation" className={menuOpen ? 'app-sidebar is-open' : 'app-sidebar'} aria-label="主导航">
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">AI</span>
          <span>
            <strong>新药情报平台</strong>
            <small>采集与决策工作台</small>
          </span>
        </div>
        <nav className="primary-nav">
          <p className="nav-section-label">工作区</p>
          {navigation.map((item) => {
            const NavigationIcon = item.icon
            return (
            <a
              className={item.path === path ? 'nav-link is-active' : 'nav-link'}
              href={item.path}
              aria-current={item.path === path ? 'page' : undefined}
              onClick={(event) => handleLink(event, item.path)}
              key={item.path}
            >
              <NavigationIcon aria-hidden />
              <span>{item.label}</span>
            </a>
            )
          })}
        </nav>
        <div className="sidebar-status">
          <span className="status-dot" aria-hidden="true" />
          <span><strong>本地监测服务</strong><small>数据仅保存在当前环境</small></span>
        </div>
      </aside>

      {menuOpen ? (
        <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setMenuOpen(false)} />
      ) : null}

      <div className="app-workspace">
        <header className="topbar">
          <button
            className="icon-button mobile-menu-button"
            type="button"
            aria-label="打开导航"
            aria-expanded={menuOpen}
            aria-controls="primary-navigation"
            onClick={() => setMenuOpen(true)}
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
          <div className="page-heading">
            <p className="eyebrow">INTELLIGENCE WORKSPACE</p>
            <h1>{current.label}</h1>
            <p>{subtitles[path]}</p>
          </div>
          <div className="account-menu">
            <button className="avatar-button" type="button" aria-label="账号设置" onClick={openAvatarEditor}>
              <span className="avatar" aria-hidden="true">
                {avatarBase64 ? <img src={avatarDataUrl(avatarBase64)} alt="" /> : username.slice(0, 1).toUpperCase()}
              </span>
              <span className="avatar-edit-badge" aria-hidden="true"><Camera /></span>
            </button>
            <span className="account-copy"><strong>{username}</strong><small aria-live="polite">{avatarFeedback || (role === 'admin' ? '管理员' : '普通用户')}</small></span>
            <button className="secondary-button logout-button" type="button" onClick={onLogout}>
              <LogOut aria-hidden="true" />
              退出登录
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content" data-scroll-root="viewport" tabIndex={-1}>
          {children}
        </main>
      </div>

      <DetailDrawer
        open={avatarEditorOpen}
        title="账号设置"
        description="管理头像与登录密码；头像重新登录后仍会保留。"
        width="compact"
        onClose={() => {
          if (!avatarSaving && !passwordSaving) setAvatarEditorOpen(false)
        }}
        footer={(
          <>
            <button className="secondary-button" type="button" disabled={avatarSaving} onClick={() => setAvatarEditorOpen(false)}>取消</button>
            <button className="primary-button" type="button" disabled={avatarSaving} onClick={() => void saveAvatar()}>
              {avatarSaving ? <LoaderCircle className="spin-icon" aria-hidden="true" /> : null}
              {avatarSaving ? '正在保存…' : '保存头像'}
            </button>
          </>
        )}
      >
        <div className="avatar-editor">
          <div className="account-role-card">
            <span>当前权限</span>
            <strong>{role === 'admin' ? '管理员' : '普通用户'}</strong>
          </div>
          <div className="avatar-editor__preview" aria-label="头像预览">
            {draftAvatar ? <img src={avatarDataUrl(draftAvatar)} alt="头像预览" /> : <span>{username.slice(0, 1).toUpperCase()}</span>}
          </div>
          <div className="avatar-editor__actions">
            <label className="secondary-button avatar-file-button">
              <ImagePlus aria-hidden="true" />
              选择图片
              <input type="file" accept="image/png,image/jpeg,image/webp" aria-label="选择头像图片" onChange={handleAvatarFile} disabled={avatarSaving} />
            </label>
            <button className="ghost-button" type="button" disabled={avatarSaving || draftAvatar === null} onClick={() => { setDraftAvatar(null); setAvatarError('') }}>
              <RotateCcw aria-hidden="true" />
              恢复默认头像
            </button>
          </div>
          <p className="avatar-editor__hint">支持 PNG、JPG、WebP，文件不超过 2MB。</p>
          {avatarError ? <p className="form-error" role="alert">{avatarError}</p> : null}
          {onPasswordChange ? (
            <section className="password-editor">
              <div className="password-editor__heading">
                <KeyRound aria-hidden="true" />
                <div><strong>修改密码</strong><small>修改成功后需要重新登录。</small></div>
              </div>
              <label>
                <span>当前密码</span>
                <input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
              </label>
              <label>
                <span>新密码</span>
                <input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
              </label>
              <label>
                <span>确认新密码</span>
                <input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
              </label>
              {passwordError ? <p className="form-error" role="alert">{passwordError}</p> : null}
              <button className="secondary-button" type="button" disabled={passwordSaving || !currentPassword || !newPassword || !confirmPassword} onClick={() => void savePassword()}>
                {passwordSaving ? <LoaderCircle className="spin-icon" aria-hidden="true" /> : <KeyRound aria-hidden="true" />}
                {passwordSaving ? '正在修改…' : '修改密码'}
              </button>
            </section>
          ) : null}
        </div>
      </DetailDrawer>
    </div>
  )
}

function avatarDataUrl(avatarBase64: string) {
  let mime = 'image/jpeg'
  if (avatarBase64.startsWith('iVBOR')) mime = 'image/png'
  if (avatarBase64.startsWith('UklGR')) mime = 'image/webp'
  return `data:${mime};base64,${avatarBase64}`
}

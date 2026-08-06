import { lazy, Suspense, useEffect } from 'react'
import { LoadingState } from './components/AsyncState'
import { useAppLocation, useNavigate } from './app/router'
import type { AppPath } from './app/router'
import { useAuth } from './auth/AuthProvider'
import { LoginPage } from './auth/LoginPage'
import { AppShell } from './layout/AppShell'

const DashboardPage = lazy(() => import('./features/dashboard').then((module) => ({ default: module.DashboardPage })))
const NoticesPage = lazy(() => import('./features/notices').then((module) => ({ default: module.NoticesPage })))
const KeywordRulesPage = lazy(() => import('./features/keywords/KeywordRulesPage').then((module) => ({ default: module.KeywordRulesPage })))
const SourceSitesPage = lazy(() => import('./features/sources/SourceSitesPage').then((module) => ({ default: module.SourceSitesPage })))
const SystemManagementPage = lazy(() => import('./features/system/SystemManagementPage').then((module) => ({ default: module.SystemManagementPage })))

type BusinessPath = Exclude<AppPath, '/login'>

export function App() {
  const auth = useAuth()
  const location = useAppLocation()
  const navigate = useNavigate()
  const businessPath: BusinessPath = location.path === '/login' ? '/' : location.path

  useEffect(() => {
    if (auth.status === 'authenticated' && location.path === '/login') {
      navigate('/', { replace: true })
    }
  }, [auth.status, location.path, navigate])

  useEffect(() => {
    if (auth.status !== 'authenticated') return
    const main = document.getElementById('main-content')
    main?.focus({ preventScroll: true })
  }, [auth.status, location.path, location.search])

  if (auth.status === 'loading') {
    return <main className="bootstrap-page"><LoadingState label="正在验证登录状态…" /></main>
  }

  if (auth.status === 'anonymous' || !auth.session) {
    return <LoginPage onLogin={auth.login} />
  }

  return (
    <AppShell
      path={businessPath}
      username={auth.session.user.username}
      avatarBase64={auth.session.user.avatarBase64}
      role={auth.session.user.role}
      onNavigate={(to) => navigate(to)}
      onLogout={auth.logout}
      onAvatarChange={auth.updateAvatar}
      onPasswordChange={auth.updatePassword}
    >
      <Suspense fallback={<LoadingState label="正在打开页面…" />}>
        {renderRoute(
          businessPath,
          auth.session.user.role === 'admin',
          (templateId) => navigate(`/system?template_id=${encodeURIComponent(templateId)}`),
        )}
      </Suspense>
    </AppShell>
  )
}

function renderRoute(
  path: BusinessPath,
  canManage: boolean,
  onUseTemplate: (templateId: string) => void,
) {
  switch (path) {
    case '/notices':
      return <NoticesPage canManage={canManage} />
    case '/keywords':
      return <KeywordRulesPage canManage={canManage} />
    case '/sources':
      return <SourceSitesPage canManage={canManage} onUseTemplate={onUseTemplate} />
    case '/system':
      return <SystemManagementPage canManage={canManage} />
    default:
      return <DashboardPage />
  }
}

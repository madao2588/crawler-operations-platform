import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { buildNoticeUrl, useNavigate } from '../../app/router'
import { useAuth } from '../../auth/AuthProvider'
import { PageToolbar } from '../../components/UiPrimitives'
import { dashboardOverviewQueryKey, fetchDashboardOverview } from './dashboard.api'
import type { DashboardOverview, KeywordHeatItem, NoticeListItem, ProjectSignalItem, SourceDistributionItem } from './dashboard.types'
import './dashboard.css'

export function DashboardPage() {
  const { client, status } = useAuth()
  const navigate = useNavigate()
  const overviewQuery = useQuery({
    queryKey: dashboardOverviewQueryKey,
    queryFn: () => fetchDashboardOverview(client),
    enabled: status === 'authenticated',
  })

  const isEmpty = useMemo(
    () => (overviewQuery.data ? isOverviewEmpty(overviewQuery.data) : false),
    [overviewQuery.data],
  )

  if (status === 'loading') {
    return (
      <section className="dashboard-page">
        <LoadingState />
      </section>
    )
  }

  if (status !== 'authenticated') {
    return (
      <section className="dashboard-page">
        <AuthState />
      </section>
    )
  }

  if (overviewQuery.isLoading) {
    return (
      <section className="dashboard-page">
        <LoadingState />
      </section>
    )
  }

  if (overviewQuery.isError) {
    return (
      <section className="dashboard-page">
        <ErrorState
          message={getErrorMessage(overviewQuery.error)}
          onRetry={() => void overviewQuery.refetch()}
        />
      </section>
    )
  }

  if (!overviewQuery.data || isEmpty) {
    return (
      <section className="dashboard-page">
        <Hero
          lastUpdatedAt={overviewQuery.data?.lastUpdatedAt ?? null}
          onRefresh={() => void overviewQuery.refetch()}
          isRefreshing={overviewQuery.isRefetching}
        />
        <EmptyState />
      </section>
    )
  }

  const overview = overviewQuery.data
  const sourceDisplayNames = new Map(
    overview.sourceDistribution.map((item) => [item.sourceSite, item.displayName || '未命名来源']),
  )

  return (
    <section className="dashboard-page">
      <Hero
        lastUpdatedAt={overview.lastUpdatedAt}
        onRefresh={() => void overviewQuery.refetch()}
        isRefreshing={overviewQuery.isRefetching}
      />

      <section className="dashboard-grid" aria-label="公告总览指标">
        <MetricCard
          title="今日新增公告"
          value={overview.metrics.todayNewNotices}
          tone="primary"
          onClick={() => navigate(buildNoticeUrl({ capturedToday: true }))}
        />
        <MetricCard
          title="申报通知"
          value={overview.metrics.projectDeclarationNotices}
          tone="accent"
          onClick={() => navigate(buildNoticeUrl({ projectSignal: '申报通知' }))}
        />
        <MetricCard
          title="结果公示"
          value={overview.metrics.resultPublicationNotices}
          tone="warm"
          onClick={() => navigate(buildNoticeUrl({ projectSignal: '结果公示' }))}
        />
        <MetricCard
          title="监测站点"
          value={overview.metrics.monitoringSiteCount}
          tone="neutral"
          onClick={() => navigate('/sources')}
        />
        <MetricCard
          title="关键词命中"
          value={overview.metrics.keywordHitNotices}
          tone="signal"
          onClick={() => navigate(buildNoticeUrl({ keywordHit: true }))}
        />
      </section>

      <div
        className="dashboard-scroll-region"
        role="region"
        aria-label="看板内容"
        data-scroll-region="content"
        tabIndex={0}
      >
        <section className="dashboard-columns">
          <Panel title="高价值公告" hint={`${overview.metrics.highPriorityNotices} 条需关注`}>
            <NoticeList
              items={overview.highValueNotices}
              emptyLabel="暂无高价值公告"
              sourceDisplayNames={sourceDisplayNames}
              onOpen={(noticeId) => navigate(buildNoticeUrl({ noticeId }))}
            />
          </Panel>

          <Panel title="最近公告">
            <NoticeList
              items={overview.recentNotices}
              emptyLabel="暂无最近公告"
              sourceDisplayNames={sourceDisplayNames}
              onOpen={(noticeId) => navigate(buildNoticeUrl({ noticeId }))}
            />
          </Panel>
        </section>

        <section className="dashboard-insights">
          <Panel title="关键词热度" className="dashboard-panel--soft">
            <KeywordHeatList
              items={overview.keywordHeat}
              onOpen={(keyword) => navigate(buildNoticeUrl({ keyword }))}
            />
          </Panel>
          <Panel title="来源站点分布" className="dashboard-panel--soft">
            <SourceDistributionList
              items={overview.sourceDistribution}
              onOpen={(sourceSite) => navigate(buildNoticeUrl({ sourceSite }))}
            />
          </Panel>
          <Panel title="项目线索分布" className="dashboard-panel--soft">
            <ProjectSignalList
              items={overview.projectSignalDistribution}
              onOpen={(projectSignal) => navigate(buildNoticeUrl({ projectSignal }))}
            />
          </Panel>
        </section>

        <Panel title="运行状态" className="dashboard-panel--status">
          <div className="dashboard-status-line">
            <span className="status-dot" aria-hidden="true" />
            <strong>服务 {runtimeStatusLabel(overview.runtime.status)}</strong>
            <span>数据库 {runtimeStatusLabel(overview.runtime.database)}</span>
            <span>调度 {runtimeStatusLabel(overview.runtime.scheduler)} · {overview.runtime.scheduledJobs} 项</span>
            <span className="dashboard-status-line__time">更新于 {overview.lastUpdatedAt ? formatDateTime(overview.lastUpdatedAt) : '暂未更新'}</span>
          </div>
        </Panel>
      </div>
    </section>
  )
}

function Hero({
  lastUpdatedAt,
  onRefresh,
  isRefreshing,
}: {
  lastUpdatedAt: string | null
  onRefresh: () => void
  isRefreshing: boolean
}) {
  return (
    <PageToolbar
      kicker={lastUpdatedAt ? `更新于 ${formatDateTime(lastUpdatedAt)}` : '等待首次同步'}
      title="今日监测概览"
      actions={(
        <button type="button" className="secondary-button" onClick={onRefresh} disabled={isRefreshing}>
          <RefreshCw aria-hidden="true" className={isRefreshing ? 'is-spinning' : ''} />
          {isRefreshing ? '正在刷新' : '刷新看板'}
        </button>
      )}
    />
  )
}

function MetricCard({
  title,
  value,
  tone,
  onClick,
}: {
  title: string
  value: number
  tone: 'primary' | 'accent' | 'warm' | 'neutral' | 'signal'
  onClick: () => void
}) {
  return (
    <button type="button" className="dashboard-card-button" data-tone={tone} onClick={onClick} aria-label={`${title} ${value}`}>
      <div className="dashboard-card-button__value">{value}</div>
      <h2 className="dashboard-card-button__title">{title}</h2>
    </button>
  )
}

function Panel({
  title,
  hint,
  className = '',
  children,
}: {
  title: string
  hint?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <section className={`dashboard-panel ${className}`.trim()}>
      <header className="dashboard-panel__header">
        <h2 className="dashboard-panel__title">{title}</h2>
        {hint ? <span className="dashboard-panel__hint">{hint}</span> : null}
      </header>
      {children}
    </section>
  )
}

function NoticeList({
  items,
  emptyLabel,
  sourceDisplayNames,
  onOpen,
}: {
  items: NoticeListItem[]
  emptyLabel: string
  sourceDisplayNames: Map<string, string>
  onOpen: (noticeId: number) => void
}) {
  if (!items.length) return <p className="dashboard-panel__hint">{emptyLabel}</p>
  return (
    <div className="dashboard-list">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="dashboard-list-button"
          onClick={() => onOpen(item.id)}
          aria-label={`${item.title} 打开公告详情`}
        >
          <span className="dashboard-list-button__title">{item.title}</span>
          <span className="dashboard-list-button__meta">
            <span>{item.projectSignal !== '其他项目线索' ? item.projectSignal : item.category}</span>
            <span>{sourceDisplayNames.get(item.sourceSite) ?? '未命名来源'}</span>
            <span>质量 {item.qualityScore}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

function KeywordHeatList({
  items,
  onOpen,
}: {
  items: KeywordHeatItem[]
  onOpen: (keyword: string) => void
}) {
  if (!items.length) return <p className="dashboard-panel__hint">暂无关键词命中热度。</p>
  return (
    <div className="dashboard-chip-grid">
      {items.map((item) => (
        <button
          key={item.keyword}
          type="button"
          className="dashboard-chip-button"
          onClick={() => onOpen(item.keyword)}
          aria-label={`${item.keyword} ${item.count}`}
        >
          <strong>{item.keyword}</strong>
          <span>{item.count}</span>
        </button>
      ))}
    </div>
  )
}

function SourceDistributionList({
  items,
  onOpen,
}: {
  items: SourceDistributionItem[]
  onOpen: (sourceSite: string) => void
}) {
  if (!items.length) return <p className="dashboard-panel__hint">暂无来源站点分布。</p>
  return (
    <div className="dashboard-bar-list">
      {items.map((item) => (
        <BarButton
          key={item.sourceSite}
          label={item.displayName || item.sourceSite}
          count={`${item.noticeCount} 条`}
          percentage={item.percentage}
          onClick={() => onOpen(item.sourceSite)}
        />
      ))}
    </div>
  )
}

function ProjectSignalList({
  items,
  onOpen,
}: {
  items: ProjectSignalItem[]
  onOpen: (projectSignal: string) => void
}) {
  if (!items.length) return <p className="dashboard-panel__hint">暂无项目线索分布。</p>
  return (
    <div className="dashboard-bar-list">
      {items.map((item) => (
        <BarButton
          key={item.label}
          label={item.label}
          count={`${item.noticeCount} 条`}
          percentage={item.percentage}
          onClick={() => onOpen(item.label)}
        />
      ))}
    </div>
  )
}

function BarButton({
  label,
  count,
  percentage,
  onClick,
}: {
  label: string
  count: string
  percentage: number
  onClick: () => void
}) {
  const width = `${Math.max(6, Math.min(percentage, 100))}%`
  return (
    <button type="button" className="dashboard-bar-button" onClick={onClick} aria-label={`${label} ${count}`}>
      <span className="dashboard-bar-button__row">
        <span className="dashboard-bar-button__label">{label}</span>
        <span className="dashboard-bar-button__count">{count}</span>
      </span>
      <span className="dashboard-bar-button__track" aria-hidden="true">
        <span className="dashboard-bar-button__fill" style={{ width }} />
      </span>
    </button>
  )
}

function runtimeStatusLabel(value?: string) {
  const normalized = value?.trim().toLowerCase()
  if (normalized === 'ok' || normalized === 'healthy') return '正常'
  if (normalized === 'running') return '运行中'
  if (normalized === 'stopped' || normalized === 'inactive') return '未运行'
  if (normalized === 'degraded' || normalized === 'warning') return '需关注'
  if (normalized === 'error' || normalized === 'failed' || normalized === 'unhealthy') return '异常'
  return value?.trim() || '未知'
}

function LoadingState() {
  return (
    <section className="dashboard-loading" aria-live="polite">
      <h2>正在加载首页看板…</h2>
      <p>正在从后端读取最新公告统计与运行状态。</p>
    </section>
  )
}

function AuthState() {
  return (
    <section className="dashboard-auth">
      <h2>请先登录</h2>
      <p>首页看板需要有效会话后才能读取监测结果。</p>
    </section>
  )
}

function EmptyState() {
  return (
    <section className="dashboard-empty">
      <h2>暂无可展示的公告与监测统计</h2>
      <p>当前还没有采集结果，或所有任务尚未产生可用于展示的业务数据。</p>
    </section>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section className="dashboard-error" role="alert">
      <h2>首页看板加载失败</h2>
      <p>{message}</p>
      <div className="dashboard-error__actions">
        <button type="button" className="dashboard-refresh" onClick={onRetry}>
          重试
        </button>
      </div>
    </section>
  )
}

function isOverviewEmpty(overview: DashboardOverview) {
  const metrics = overview.metrics
  return (
    metrics.todayNewNotices === 0 &&
    metrics.keywordHitNotices === 0 &&
    metrics.monitoringSiteCount === 0 &&
    metrics.highPriorityNotices === 0 &&
    metrics.highQualityNotices === 0 &&
    metrics.projectDeclarationNotices === 0 &&
    metrics.resultPublicationNotices === 0 &&
    overview.highValueNotices.length === 0 &&
    overview.recentNotices.length === 0 &&
    overview.keywordHeat.length === 0 &&
    overview.sourceDistribution.length === 0 &&
    overview.projectSignalDistribution.length === 0
  )
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '服务返回异常，请稍后重试。'
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronRight, RefreshCw } from 'lucide-react'
import { buildNoticeUrl, useNavigate } from '../../app/router'
import { useAuth } from '../../auth/AuthProvider'
import { DetailDrawer, PageToolbar } from '../../components/UiPrimitives'
import { dashboardOverviewQueryKey, fetchDashboardOverview } from './dashboard.api'
import type { DashboardCollectionIssue, DashboardOverview, KeywordHeatItem, NoticeListItem, ProjectSignalItem, SourceDistributionItem } from './dashboard.types'
import { COLLECTION_COMPLETENESS_HELP, collectionCompletenessLabel } from '../../utils/completeness'
import type { RunAllEnabledResult } from '../system/types'
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

      <CollectionHealthAlert
        health={overview.collectionHealth}
        onRefresh={() => overviewQuery.refetch()}
      />

      <section className="dashboard-grid" aria-label="公告总览指标">
        <MetricCard
          title="今日发布公告"
          value={overview.metrics.todayNewNotices}
          tone="primary"
          onClick={() => navigate(buildNoticeUrl({ businessToday: true }))}
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
            <span>版本 {overview.runtime.releaseVersion}</span>
            <span className="dashboard-status-line__time">更新于 {overview.lastUpdatedAt ? formatDateTime(overview.lastUpdatedAt) : '暂未更新'}</span>
          </div>
        </Panel>
      </div>
    </section>
  )
}

function CollectionHealthAlert({
  health,
  onRefresh,
}: {
  health: DashboardOverview['collectionHealth']
  onRefresh: () => Promise<unknown>
}) {
  const { client, session } = useAuth()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [rerunningTaskId, setRerunningTaskId] = useState<number | null>(null)
  const [bulkRunning, setBulkRunning] = useState(false)
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)
  if (health.status !== 'warning' && health.status !== 'error') return null
  const isStale = health.staleTaskCount > 0
  const freshness = health.lastSuccessAt
    ? `数据截至 ${formatFullDateTime(health.lastSuccessAt)}`
    : '尚无成功采集记录'
  const issues = [
    health.failedTaskCount > 0 ? `${health.failedTaskCount} 个来源最近运行失败` : null,
    health.partialTaskCount > 0 ? `${health.partialTaskCount} 个来源本次部分失败` : null,
    health.staleTaskCount > 0 ? `${health.staleTaskCount} 个来源超过 24 小时未成功更新` : null,
  ].filter((item): item is string => item !== null)
  const issueGroups = groupCollectionIssues(health.issues)

  async function rerun(taskId: number, taskName: string) {
    if (rerunningTaskId !== null || bulkRunning) return
    setRerunningTaskId(taskId)
    setFeedback(null)
    try {
      await client.post(`/v1/tasks/${taskId}/run`)
      setFeedback({ tone: 'success', message: `${taskName}已提交重跑，可在系统管理查看进度。` })
    } catch (error) {
      setFeedback({ tone: 'error', message: `重跑失败：${getErrorMessage(error)}` })
    } finally {
      setRerunningTaskId(null)
    }
  }

  async function runAllEnabled() {
    if (bulkRunning || rerunningTaskId !== null) return
    setBulkRunning(true)
    setFeedback(null)
    try {
      const result = await client.post<RunAllEnabledResult>('/v1/tasks/run-enabled')
      setFeedback({
        tone: result.errors.length ? 'error' : 'success',
        message: summarizeBulkRun(result),
      })
      await onRefresh()
    } catch (error) {
      setFeedback({ tone: 'error', message: `批量更新失败：${getErrorMessage(error)}` })
    } finally {
      setBulkRunning(false)
    }
  }

  return (
    <>
      <div className="dashboard-collection-alert" role="alert">
        <AlertTriangle aria-hidden="true" />
        <div className="dashboard-collection-alert__copy">
          <div className="dashboard-collection-alert__headline">
            <strong>{isStale ? '采集数据已过期' : '采集运行异常'}</strong>
            <span>{issues.join(' · ')}</span>
          </div>
          <span className="dashboard-collection-alert__freshness">{freshness}</span>
        </div>
        <div className="dashboard-collection-alert__actions">
          {session?.user.role === 'admin' ? (
            <button
              type="button"
              className="dashboard-collection-alert__bulk"
              disabled={bulkRunning || rerunningTaskId !== null}
              onClick={() => void runAllEnabled()}
            >
              <RefreshCw aria-hidden="true" className={bulkRunning ? 'is-spinning' : ''} />
              {bulkRunning ? '正在更新' : '更新全部来源'}
            </button>
          ) : null}
          {health.issues.length ? (
            <button
              type="button"
              className="dashboard-collection-alert__details-button"
              aria-haspopup="dialog"
              onClick={() => setDetailsOpen(true)}
            >
              查看 {health.issues.length} 个异常
              <ChevronRight aria-hidden="true" />
            </button>
          ) : null}
        </div>
      </div>

      {feedback ? (
        <div className={`dashboard-collection-alert__feedback is-${feedback.tone}`} role="status">
          {feedback.message}
        </div>
      ) : null}

      <DetailDrawer
        open={detailsOpen}
        title="采集异常详情"
        description={`${issues.join('；')}。${freshness}`}
        width="wide"
        onClose={() => setDetailsOpen(false)}
      >
        <div className="dashboard-collection-details">
          {issueGroups.map((group) => (
            <section className="dashboard-collection-details__group" key={group.reason}>
              <header className="dashboard-collection-details__group-header">
                <div>
                  <span>失败原因</span>
                  <h3>{group.reason}</h3>
                </div>
                <strong>{group.issues.length} 个来源</strong>
              </header>
              <div className="dashboard-collection-details__list">
                {group.issues.map((issue) => (
                  <div className="dashboard-collection-details__item" key={issue.taskId}>
                    <span className="dashboard-collection-details__name">{issue.taskName}</span>
                    <div className="dashboard-collection-details__states">
                      <span className={`dashboard-collection-alert__status is-${issue.status}`}>
                        {collectionIssueLabel(issue.status)}
                      </span>
                      {issue.isStale ? <span className="dashboard-collection-alert__status is-stale">已过期</span> : null}
                    </div>
                    {session?.user.role === 'admin' ? (
                      <button
                        type="button"
                        className="dashboard-collection-alert__retry"
                        aria-label={`重新运行 ${issue.taskName}`}
                        disabled={rerunningTaskId !== null || bulkRunning}
                        onClick={() => void rerun(issue.taskId, issue.taskName)}
                      >
                        <RefreshCw aria-hidden="true" className={rerunningTaskId === issue.taskId ? 'is-spinning' : ''} />
                        {rerunningTaskId === issue.taskId ? '提交中' : '重新运行'}
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </DetailDrawer>
    </>
  )
}

function groupCollectionIssues(issues: DashboardCollectionIssue[]) {
  const groups = new Map<string, DashboardCollectionIssue[]>()
  issues.forEach((issue) => {
    const reason = issue.reason.trim() || '未提供具体失败原因'
    groups.set(reason, [...(groups.get(reason) ?? []), issue])
  })
  return Array.from(groups, ([reason, groupedIssues]) => ({ reason, issues: groupedIssues }))
}

function summarizeBulkRun(result: RunAllEnabledResult) {
  const messages: string[] = []
  if (result.queued_task_ids.length) messages.push(`已提交 ${result.queued_task_ids.length} 个来源`)
  if (result.skipped_task_ids.length) messages.push(`${result.skipped_task_ids.length} 个正在运行的来源已跳过`)
  if (result.recovered_task_ids.length) messages.push(`${result.recovered_task_ids.length} 个卡住的任务已恢复`)
  if (result.errors.length) messages.push(`${result.errors.length} 个来源提交失败`)
  return messages.length ? `${messages.join('，')}。` : '当前没有可更新的启用来源。'
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
            <span title={COLLECTION_COMPLETENESS_HELP} aria-label={collectionCompletenessLabel(item.qualityScore)}>
              {collectionCompletenessLabel(item.qualityScore)}
            </span>
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

function collectionIssueLabel(status: string) {
  if (status === 'partial') return '部分完成'
  if (status === 'stale') return '未及时更新'
  return '运行失败'
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

function formatFullDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

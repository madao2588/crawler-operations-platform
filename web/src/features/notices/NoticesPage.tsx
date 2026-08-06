import { useEffect, useMemo, useState } from 'react'
import { Filter, RotateCcw } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  buildNoticeUrl,
  readNoticeQuery,
  type NoticeQuery,
  useAppLocation,
  useNavigate,
} from '../../app/router'
import { useAuth } from '../../auth/AuthProvider'
import { DetailDrawer, PageToolbar } from '../../components/UiPrimitives'
import './notices.css'

interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

interface NoticeItem {
  id: number
  title: string
  summary: string
  source_site: string
  source_url: string
  published_at: string | null
  captured_at: string | null
  quality_score: number
  matched_keywords: string[]
  is_high_priority: boolean
  project_signal: string
  category: string
  ai_summary: string | null
  review_status: string
  is_archived: boolean
  remark: string | null
  task_id: number
}

interface NoticeDetail extends NoticeItem {
  content_text: string
  content_html: string
  content_hash: string | null
  snapshot_path: string | null
  metadata: Record<string, unknown> | null
}

interface NoticeSourceSiteOption {
  source_site: string
  display_name: string
}

interface NoticeMonthOption {
  month: string
  count: number
}

interface NoticeSnapshot {
  id: number
  source_url: string
  source_site: string
  snapshot_path: string
  content: string
}

interface CountState {
  total: number
  highPriority: number
  keywordHit: number
}

const pageSize = 20
const reviewOptions = ['待关注', '已跟进', '已忽略']
const knownCategories = ['项目申报通知', '结果公示', '行业会议', '竞品文献']

export function NoticesPage({ canManage = true }: { canManage?: boolean }) {
  const { client } = useAuth()
  const location = useAppLocation()
  const navigate = useNavigate()
  const currentQuery = useMemo(() => readNoticeQuery(location.search), [location.search])
  const selectedNoticeId = currentQuery.noticeId ?? null

  const [searchDraft, setSearchDraft] = useState(currentQuery.keyword ?? '')
  const [page, setPage] = useState(1)
  const [listState, setListState] = useState<LoadState<PageData<NoticeItem>>>({ status: 'loading' })
  const [detailState, setDetailState] = useState<LoadState<NoticeDetail>>({ status: 'idle' })
  const [sourceSitesState, setSourceSitesState] = useState<LoadState<NoticeSourceSiteOption[]>>({
    status: 'loading',
  })
  const [monthsState, setMonthsState] = useState<LoadState<NoticeMonthOption[]>>({
    status: 'loading',
  })
  const [monthsReloadVersion, setMonthsReloadVersion] = useState(0)
  const [countState, setCountState] = useState<LoadState<CountState>>({ status: 'loading' })
  const [feedback, setFeedback] = useState<string | null>(null)
  const [reviewPending, setReviewPending] = useState<string | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [snapshotState, setSnapshotState] = useState<LoadState<NoticeSnapshot> & { open: boolean }>({
    status: 'idle',
    open: false,
  })

  useEffect(() => {
    setSearchDraft(currentQuery.keyword ?? '')
  }, [currentQuery.keyword])

  useEffect(() => {
    setPage(1)
  }, [
    currentQuery.keyword,
    currentQuery.month,
    currentQuery.category,
    currentQuery.reviewStatus,
    currentQuery.archived,
    currentQuery.capturedToday,
    currentQuery.sourceSite,
    currentQuery.keywordHit,
    currentQuery.highPriority,
    currentQuery.highQuality,
    currentQuery.projectSignal,
  ])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setSourceSitesState((prev) => (prev.status === 'success' ? prev : { status: 'loading' }))
    client
      .get<NoticeSourceSiteOption[]>('/v1/notices/source-sites', { signal: controller.signal })
      .then((data) => {
        if (active) setSourceSitesState({ status: 'success', data })
      })
      .catch((error) => {
        if (!active || controller.signal.aborted) return
        setSourceSitesState({ status: 'error', error: toErrorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setMonthsState({ status: 'loading' })
    client
      .get<NoticeMonthOption[]>('/v1/notices/months', {
        signal: controller.signal,
        query: buildMonthQuery(currentQuery),
      })
      .then((data) => {
        if (active) setMonthsState({ status: 'success', data })
      })
      .catch((error) => {
        if (!active || controller.signal.aborted) return
        setMonthsState({ status: 'error', error: toErrorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [
    client,
    monthsReloadVersion,
    currentQuery.keyword,
    currentQuery.category,
    currentQuery.reviewStatus,
    currentQuery.archived,
    currentQuery.capturedToday,
    currentQuery.sourceSite,
    currentQuery.keywordHit,
    currentQuery.highPriority,
    currentQuery.highQuality,
    currentQuery.projectSignal,
  ])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setListState({ status: 'loading' })
    setFeedback(null)
    client
      .get<PageData<NoticeItem>>('/v1/notices', {
        signal: controller.signal,
        query: buildListQuery(currentQuery, page),
      })
      .then((data) => {
        if (!active) return
        setListState({ status: 'success', data })
      })
      .catch((error) => {
        if (!active || controller.signal.aborted) return
        setListState({ status: 'error', error: toErrorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, currentQuery, page])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setCountState({ status: 'loading' })
    Promise.all([
      fetchCount(client, currentQuery, {}, controller.signal),
      fetchCount(client, currentQuery, { highPriority: true }, controller.signal),
      fetchCount(client, currentQuery, { keywordHit: true }, controller.signal),
    ])
      .then(([total, highPriority, keywordHit]) => {
        if (active) setCountState({ status: 'success', data: { total, highPriority, keywordHit } })
      })
      .catch((error) => {
        if (!active || controller.signal.aborted) return
        setCountState({ status: 'error', error: toErrorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, currentQuery])

  useEffect(() => {
    if (!selectedNoticeId) {
      setDetailState({ status: 'idle' })
      return
    }
    let active = true
    const controller = new AbortController()
    setDetailState({ status: 'loading' })
    client
      .get<NoticeDetail>(`/v1/notices/${selectedNoticeId}`, { signal: controller.signal })
      .then((data) => {
        if (active) setDetailState({ status: 'success', data })
      })
      .catch((error) => {
        if (!active || controller.signal.aborted) return
        setDetailState({ status: 'error', error: toErrorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, selectedNoticeId])

  const sourceSites = sourceSitesState.status === 'success' ? sourceSitesState.data : []
  const sourceNameMap = useMemo(
    () => new Map(sourceSites.map((site) => [site.source_site, site.display_name])),
    [sourceSites],
  )

  const categories = useMemo(() => {
    const values = new Set(knownCategories)
    if (listState.status === 'success') {
      for (const item of listState.data.items) values.add(item.category)
    }
    if (currentQuery.category) values.add(currentQuery.category)
    return Array.from(values)
  }, [currentQuery.category, listState])

  const activeFilters = buildActiveFilters(currentQuery, sourceNameMap)
  const totalPages =
    listState.status === 'success' ? Math.max(1, Math.ceil(listState.data.total / pageSize)) : 1

  return (
    <main className="notices-page">
      <PageToolbar
        title="筛选与处理"
        actions={
          <>
            <div className="notices-feedback" aria-live="polite">
              {feedback ? <span className="notice-feedback-pill">{feedback}</span> : null}
            </div>
            <button
              type="button"
              className="secondary-action"
              aria-expanded={filtersOpen}
              aria-controls="notice-filters"
              onClick={() => setFiltersOpen((value) => !value)}
            >
              <Filter aria-hidden="true" />
              {filtersOpen ? '收起筛选' : '展开筛选'}
            </button>
          </>
        }
      />

      <section className="notices-card-grid" aria-label="公告统计">
        <SummaryCard
          title="全部公告"
          value={countState.status === 'success' ? countState.data.total : '...'}
          active={!currentQuery.highPriority && !currentQuery.keywordHit}
          onClick={() => replaceQuery(navigate, currentQuery, { highPriority: undefined, keywordHit: undefined })}
        />
        <SummaryCard
          title="高优先级公告"
          value={countState.status === 'success' ? countState.data.highPriority : '...'}
          active={currentQuery.highPriority === true}
          onClick={() => replaceQuery(navigate, currentQuery, { highPriority: true, keywordHit: undefined })}
        />
        <SummaryCard
          title="关键词命中"
          value={countState.status === 'success' ? countState.data.keywordHit : '...'}
          active={currentQuery.keywordHit === true}
          onClick={() => replaceQuery(navigate, currentQuery, { keywordHit: true, highPriority: undefined })}
        />
      </section>

      <MonthFilterBar
        state={monthsState}
        selectedMonth={currentQuery.month}
        onSelect={(month) =>
          replaceQuery(
            navigate,
            currentQuery,
            month ? { month, capturedToday: undefined } : { month: undefined },
          )
        }
        onRetry={() => setMonthsReloadVersion((value) => value + 1)}
      />

      {activeFilters.length > 0 ? (
        <section className="active-filter-bar" aria-label="当前筛选条件">
          <strong>当前条件</strong>
          <div className="filter-chip-list">
            {activeFilters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                className="filter-chip"
                onClick={() => replaceQuery(navigate, currentQuery, { [filter.key]: undefined } as Partial<NoticeQuery>)}
              >
                <span>{filter.label}</span>
                <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
          <button type="button" className="text-action" onClick={() => navigate('/notices', { replace: true })}>
            清除全部
          </button>
        </section>
      ) : null}

      <section className={`notices-layout ${filtersOpen ? 'has-filters' : ''}`}>
        <aside id="notice-filters" className={`notices-sidebar ${filtersOpen ? 'is-open' : ''}`} aria-label="筛选条件">
          <form
            className="notice-panel"
            onSubmit={(event) => {
              event.preventDefault()
              replaceQuery(navigate, currentQuery, { keyword: searchDraft || undefined })
            }}
          >
            <div className="panel-header">
              <h2>筛选条件</h2>
              <button
                type="button"
                className="text-action"
                onClick={() => {
                  setSearchDraft('')
                  navigate('/notices', { replace: true })
                }}
              >
                清空
              </button>
            </div>

            <label className="field">
              <span>搜索关键词</span>
              <input
                name="keyword"
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                placeholder="按标题、摘要搜索"
              />
            </label>

            <label className="field">
              <span>来源机构</span>
              <select
                value={currentQuery.sourceSite ?? ''}
                onChange={(event) =>
                  replaceQuery(navigate, currentQuery, {
                    sourceSite: event.target.value || undefined,
                  })
                }
              >
                <option value="">全部来源</option>
                {sourceSites.map((site) => (
                  <option key={site.source_site} value={site.source_site}>
                    {site.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>类别</span>
              <select
                value={currentQuery.category ?? ''}
                onChange={(event) =>
                  replaceQuery(navigate, currentQuery, {
                    category: event.target.value || undefined,
                  })
                }
              >
                <option value="">全部类别</option>
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>信息类型</span>
              <select
                value={currentQuery.projectSignal ?? ''}
                onChange={(event) =>
                  replaceQuery(navigate, currentQuery, {
                    projectSignal: event.target.value || undefined,
                  })
                }
              >
                <option value="">全部类型</option>
                <option value="申报通知">申报通知</option>
                <option value="结果公示">结果公示</option>
                <option value="其他项目线索">其他项目线索</option>
              </select>
            </label>

            <label className="field">
              <span>跟进状态</span>
              <select
                value={currentQuery.reviewStatus ?? ''}
                onChange={(event) =>
                  replaceQuery(navigate, currentQuery, {
                    reviewStatus: event.target.value || undefined,
                  })
                }
              >
                <option value="">全部状态</option>
                {reviewOptions.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>

            <div className="toggle-group" role="group" aria-label="快速过滤">
              <ToggleButton
                label="仅今日采集"
                active={currentQuery.capturedToday === true}
                onClick={() => {
                  const capturedToday = currentQuery.capturedToday ? undefined : true
                  replaceQuery(navigate, currentQuery, {
                    capturedToday,
                    month: capturedToday ? undefined : currentQuery.month,
                  })
                }}
              />
              <ToggleButton
                label="仅已归档"
                active={currentQuery.archived === true}
                onClick={() =>
                  replaceQuery(navigate, currentQuery, {
                    archived: currentQuery.archived ? undefined : true,
                  })
                }
              />
            </div>

            <button type="submit" className="primary-action">
              应用筛选
            </button>
          </form>

        </aside>

        <section className="notices-list-panel notice-panel" aria-label="公告列表">
          <div className="panel-header">
            <div>
              <h2>公告列表</h2>
              <p className="panel-meta">
                {listState.status === 'success' ? `共 ${listState.data.total} 条，当前第 ${page} 页` : '正在同步公告数据'}
              </p>
            </div>
            <button type="button" className="text-action" onClick={() => setPage(1)}>
              <RotateCcw aria-hidden="true" />
              回到第一页
            </button>
          </div>

          {listState.status === 'loading' ? <LoadingPanel label="公告列表加载中" /> : null}
          {listState.status === 'error' ? (
            <ErrorPanel label={listState.error} onRetry={() => setPage((value) => value)} />
          ) : null}
          {listState.status === 'success' && listState.data.items.length === 0 ? (
            <EmptyPanel title="没有符合条件的公告" description="放宽来源、状态或关键词后再试。" />
          ) : null}
          {listState.status === 'success' ? (
            <>
              <div
                className="notice-list"
                role="region"
                aria-label="公告结果"
                data-scroll-region="list"
                tabIndex={0}
              >
                {listState.data.items.map((item) => {
                  const selected = item.id === selectedNoticeId
                  const sourceName = sourceNameMap.get(item.source_site) ?? item.source_site
                  return (
                    <article key={item.id} className={`notice-card ${selected ? 'is-selected' : ''}`} aria-label={item.title}>
                      <div
                        className="notice-card-hitbox"
                        role="button"
                        tabIndex={0}
                        onClick={() => replaceQuery(navigate, currentQuery, { noticeId: item.id })}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            replaceQuery(navigate, currentQuery, { noticeId: item.id })
                          }
                        }}
                      >
                        <div className="notice-card-topline">
                          <span className="notice-badge-row">
                            <span className={`priority-badge ${item.is_high_priority ? 'is-hot' : ''}`}>
                              {item.is_high_priority ? '高优先级' : '常规'}
                            </span>
                            <span className="quality-badge">质量 {item.quality_score}</span>
                          </span>
                          <span className="meta-copy notice-card-time">
                            <span className="notice-date-basis">
                              {item.published_at ? '发布日期' : '采集日期'}
                            </span>
                            <span>{formatDate(item.published_at ?? item.captured_at)}</span>
                          </span>
                        </div>
                        <h3>{item.title}</h3>
                        <p>{item.summary || item.ai_summary || '暂无摘要'}</p>
                        <div className="notice-card-controls">
                          <button
                            type="button"
                            className="ghost-chip"
                            aria-label={`来源 ${sourceName}`}
                            onClick={(event) => {
                              event.stopPropagation()
                              replaceQuery(navigate, currentQuery, { sourceSite: item.source_site })
                            }}
                          >
                            {sourceName}
                          </button>
                          <button
                            type="button"
                            className="ghost-chip"
                            onClick={(event) => {
                              event.stopPropagation()
                              if (item.project_signal !== '其他项目线索') {
                                replaceQuery(navigate, currentQuery, {
                                  projectSignal: item.project_signal,
                                })
                              } else {
                                replaceQuery(navigate, currentQuery, { category: item.category })
                              }
                            }}
                          >
                            {item.project_signal !== '其他项目线索'
                              ? item.project_signal
                              : item.category}
                          </button>
                          {item.matched_keywords.slice(0, 1).map((keyword) => (
                            <button
                              key={keyword}
                              type="button"
                              className="keyword-chip"
                              onClick={(event) => {
                                event.stopPropagation()
                                replaceQuery(navigate, currentQuery, { keyword })
                              }}
                            >
                              {keyword}
                            </button>
                          ))}
                          {item.matched_keywords.length > 1 ? (
                            <span className="keyword-count">另有 {item.matched_keywords.length - 1} 个命中</span>
                          ) : null}
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>

              <footer className="pagination-row">
                <button type="button" className="secondary-action" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                  上一页
                </button>
                <span>
                  第 {page} / {totalPages} 页
                </span>
                <button
                  type="button"
                  className="secondary-action"
                  disabled={page >= totalPages}
                  onClick={() => setPage((value) => value + 1)}
                >
                  下一页
                </button>
              </footer>
            </>
          ) : null}
        </section>

      </section>

      <DetailDrawer
        open={Boolean(selectedNoticeId)}
        title="公告详情"
        description="核对内容、命中原因与跟进状态"
        width="wide"
        onClose={() => replaceQuery(navigate, currentQuery, { noticeId: undefined })}
      >
        <section className="notice-detail-panel" role="region" aria-label="公告详情">
          {detailState.status === 'idle' ? (
            <EmptyPanel title="请选择一条公告" description="详情中会展示原文摘要、标签和处理动作。" />
          ) : null}
          {detailState.status === 'loading' ? <LoadingPanel label="公告详情加载中" /> : null}
          {detailState.status === 'error' ? (
            <ErrorPanel label={detailState.error} onRetry={() => replaceQuery(navigate, currentQuery, { noticeId: selectedNoticeId ?? undefined })} />
          ) : null}
          {detailState.status === 'success' ? (
            <NoticeDetailView
              detail={detailState.data}
              sourceName={sourceNameMap.get(detailState.data.source_site) ?? detailState.data.source_site}
              canManage={canManage}
              reviewPending={reviewPending}
              onSourceClick={() => replaceQuery(navigate, currentQuery, { sourceSite: detailState.data.source_site })}
              onCategoryClick={() => replaceQuery(navigate, currentQuery, { category: detailState.data.category })}
              onProjectSignalClick={() =>
                replaceQuery(navigate, currentQuery, {
                  projectSignal: detailState.data.project_signal,
                })
              }
              onKeywordClick={(keyword) => replaceQuery(navigate, currentQuery, { keyword })}
              onReviewChange={(reviewStatus) => updateReview(client, detailState.data, { review_status: reviewStatus })}
              onArchiveToggle={() => updateArchive(client, detailState.data)}
              onSnapshotOpen={() => openSnapshot(client, detailState.data.id)}
            />
          ) : null}
        </section>
      </DetailDrawer>

      {snapshotState.open ? (
        <section className="snapshot-overlay" role="dialog" aria-label="采集快照">
          <div className="snapshot-dialog">
            <div className="panel-header">
              <div>
                <h2>采集快照</h2>
                <p className="panel-meta">用于核对抓取原文和命中原因。</p>
              </div>
              <button type="button" className="text-action" onClick={() => setSnapshotState({ status: 'idle', open: false })}>
                关闭
              </button>
            </div>
            {snapshotState.status === 'loading' ? <LoadingPanel label="快照加载中" /> : null}
            {snapshotState.status === 'error' ? (
              <ErrorPanel label={snapshotState.error} onRetry={() => openSnapshot(client, selectedNoticeId ?? 0)} />
            ) : null}
            {snapshotState.status === 'success' ? <pre className="snapshot-content">{snapshotState.data.content}</pre> : null}
          </div>
        </section>
      ) : null}
    </main>
  )

  function updateReview(apiClient: typeof client, detail: NoticeDetail, patch: { review_status?: string }) {
    const actionLabel = patch.review_status ? `review-${patch.review_status}` : 'review'
    setReviewPending(actionLabel)
    setFeedback(null)
    apiClient
      .patch<NoticeDetail>(`/v1/notices/${detail.id}/review`, {
        review_status: patch.review_status ?? detail.review_status,
        is_archived: detail.is_archived,
        remark: detail.remark,
      })
      .then((data) => {
        setDetailState({ status: 'success', data })
        setFeedback(`已更新为“${data.review_status}”`)
        reloadList()
      })
      .catch((error) => {
        setFeedback(toErrorMessage(error))
      })
      .finally(() => {
        setReviewPending(null)
      })
  }

  function updateArchive(apiClient: typeof client, detail: NoticeDetail) {
    const nextArchived = !detail.is_archived
    const confirmMessage = nextArchived ? '确认归档这条公告？' : '确认取消归档这条公告？'
    if (!window.confirm(confirmMessage)) return
    setReviewPending('archive')
    setFeedback(null)
    apiClient
      .patch<NoticeDetail>(`/v1/notices/${detail.id}/review`, {
        review_status: detail.review_status,
        is_archived: nextArchived,
        remark: detail.remark,
      })
      .then((data) => {
        setDetailState({ status: 'success', data })
        setFeedback(nextArchived ? '公告已归档' : '公告已取消归档')
        reloadList()
      })
      .catch((error) => {
        setFeedback(toErrorMessage(error))
      })
      .finally(() => {
        setReviewPending(null)
      })
  }

  function openSnapshot(apiClient: typeof client, noticeId: number) {
    if (!noticeId) return
    setSnapshotState({ status: 'loading', open: true })
    apiClient
      .get<NoticeSnapshot>(`/v1/notices/${noticeId}/snapshot`)
      .then((data) => {
        setSnapshotState({ status: 'success', data, open: true })
      })
      .catch((error) => {
        setSnapshotState({ status: 'error', error: toErrorMessage(error), open: true })
      })
  }

  function reloadList() {
    client
      .get<PageData<NoticeItem>>('/v1/notices', { query: buildListQuery(currentQuery, page) })
      .then((data) => setListState({ status: 'success', data }))
      .catch((error) => setListState({ status: 'error', error: toErrorMessage(error) }))
  }
}

function NoticeDetailView(props: {
  detail: NoticeDetail
  sourceName: string
  canManage: boolean
  reviewPending: string | null
  onSourceClick: () => void
  onCategoryClick: () => void
  onProjectSignalClick: () => void
  onKeywordClick: (keyword: string) => void
  onReviewChange: (reviewStatus: string) => void
  onArchiveToggle: () => void
  onSnapshotOpen: () => void
}) {
  const { detail, sourceName, reviewPending } = props

  return (
    <article className="detail-card">
      <div className="notice-card-topline">
        <span className={`priority-badge ${detail.is_high_priority ? 'is-hot' : ''}`}>
          {detail.is_high_priority ? '高优先级' : '常规'}
        </span>
        <span className="quality-badge">质量 {detail.quality_score}</span>
      </div>
      <h3>{detail.title}</h3>
      <p className="detail-summary">{detail.ai_summary || detail.summary || '暂无摘要'}</p>
      <dl className="detail-date-grid" aria-label="公告时间">
        <div>
          <dt>发布日期</dt>
          <dd>{formatFullDate(detail.published_at)}</dd>
        </div>
        <div>
          <dt>采集时间</dt>
          <dd>{formatFullDate(detail.captured_at)}</dd>
        </div>
      </dl>
      <div className="detail-chip-row">
        <button type="button" className="ghost-chip" aria-label={`来源 ${sourceName}`} onClick={props.onSourceClick}>
          {sourceName}
        </button>
        <button
          type="button"
          className="ghost-chip"
          onClick={
            detail.project_signal !== '其他项目线索'
              ? props.onProjectSignalClick
              : props.onCategoryClick
          }
        >
          {detail.project_signal !== '其他项目线索'
            ? detail.project_signal
            : detail.category}
        </button>
        <span className="status-pill">{detail.review_status}</span>
        {detail.is_archived ? <span className="status-pill archived">已归档</span> : null}
      </div>

      <section className="detail-section">
        <h4>命中关键词</h4>
        <div className="detail-chip-row">
          {detail.matched_keywords.length === 0 ? <span className="empty-copy">当前未命中关键词。</span> : null}
          {detail.matched_keywords.map((keyword) => (
            <button
              key={keyword}
              type="button"
              className="keyword-chip"
              aria-label={`关键词 ${keyword}`}
              onClick={() => props.onKeywordClick(keyword)}
            >
              {keyword}
            </button>
          ))}
        </div>
      </section>

      <section className="detail-section">
        <h4>处理动作</h4>
        {props.canManage ? (
          <div className="detail-action-row">
            {reviewOptions.map((status) => (
              <button
                key={status}
                type="button"
                className={status === detail.review_status ? 'secondary-action active' : 'secondary-action'}
                disabled={reviewPending !== null}
                onClick={() => props.onReviewChange(status)}
              >
                {reviewPending === `review-${status}` ? '处理中...' : status}
              </button>
            ))}
          </div>
        ) : (
          <p className="read-only-banner">普通用户可查看详情，但不能修改跟进状态或归档。</p>
        )}
        <div className="detail-action-row">
          {props.canManage ? (
            <button
              type="button"
              className="secondary-action"
              disabled={reviewPending !== null}
              aria-label={detail.is_archived ? '取消归档公告' : '归档公告'}
              onClick={props.onArchiveToggle}
            >
              {reviewPending === 'archive' ? '处理中...' : detail.is_archived ? '取消归档' : '归档公告'}
            </button>
          ) : null}
          <button type="button" className="primary-action" aria-label="查看采集快照" onClick={props.onSnapshotOpen}>
            查看采集快照
          </button>
          <a className="text-link" href={detail.source_url} target="_blank" rel="noreferrer">
            查看原文
          </a>
        </div>
      </section>

      <section className="detail-section">
        <h4>正文内容</h4>
        <div className="detail-content">{detail.content_text || '暂无正文内容。'}</div>
      </section>
    </article>
  )
}

function MonthFilterBar(props: {
  state: LoadState<NoticeMonthOption[]>
  selectedMonth?: string
  onSelect: (month?: string) => void
  onRetry: () => void
}) {
  const months = props.state.status === 'success' ? props.state.data : []
  const quickMonths = months.slice(0, 5)
  const olderMonths = months.slice(5)
  const selectedInQuick = quickMonths.some((item) => item.month === props.selectedMonth)
  const selectedKnown = months.some((item) => item.month === props.selectedMonth)
  const olderOptions =
    props.selectedMonth && !selectedKnown
      ? [{ month: props.selectedMonth, count: 0 }, ...olderMonths]
      : olderMonths
  const allCount = months.reduce((sum, item) => sum + item.count, 0)

  return (
    <section className="notice-month-bar" aria-label="按月筛选">
      <strong className="notice-month-title">按月查看</strong>
      <div className="notice-month-track">
        <button
          type="button"
          className={`month-chip ${props.selectedMonth ? '' : 'is-active'}`}
          aria-pressed={!props.selectedMonth}
          onClick={() => props.onSelect(undefined)}
        >
          <span>全部月份</span>
          {props.state.status === 'success' ? <strong>{allCount}</strong> : null}
        </button>

        {props.state.status === 'loading' ? (
          <div className="month-loading" role="status" aria-label="月份加载中">
            <span />
            <span />
            <span />
          </div>
        ) : null}

        {props.state.status === 'error' ? (
          <button type="button" className="month-retry" onClick={props.onRetry}>
            月份加载失败，点击重试
          </button>
        ) : null}

        {quickMonths.map((item) => (
          <button
            key={item.month}
            type="button"
            className={`month-chip ${props.selectedMonth === item.month ? 'is-active' : ''}`}
            aria-pressed={props.selectedMonth === item.month}
            onClick={() => props.onSelect(item.month)}
          >
            <span>{formatMonthLabel(item.month)}</span>
            <strong>{item.count}</strong>
          </button>
        ))}

        {props.state.status === 'success' && months.length === 0 ? (
          <span className="month-empty">暂无可用月份</span>
        ) : null}
      </div>

      {props.state.status === 'success' && olderOptions.length > 0 ? (
        <select
          className={`month-more-select ${props.selectedMonth && !selectedInQuick ? 'is-active' : ''}`}
          aria-label="更多月份"
          value={props.selectedMonth && !selectedInQuick ? props.selectedMonth : ''}
          onChange={(event) => {
            if (event.target.value) props.onSelect(event.target.value)
          }}
        >
          <option value="">更多月份</option>
          {olderOptions.map((item) => (
            <option key={item.month} value={item.month}>
              {formatMonthLabel(item.month)} · {item.count}
            </option>
          ))}
        </select>
      ) : null}
    </section>
  )
}

function SummaryCard(props: {
  title: string
  value: number | string
  active: boolean
  onClick: () => void
}) {
  return (
    <button type="button" className={`summary-card ${props.active ? 'is-active' : ''}`} onClick={props.onClick}>
      <span className="summary-label">{props.title}</span>
      <strong>{props.value}</strong>
    </button>
  )
}

function ToggleButton(props: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`toggle-chip ${props.active ? 'is-active' : ''}`} onClick={props.onClick}>
      {props.label}
    </button>
  )
}

function LoadingPanel(props: { label: string }) {
  return (
    <div className="panel-state" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <span>{props.label}</span>
    </div>
  )
}

function ErrorPanel(props: { label: string; onRetry: () => void }) {
  return (
    <div className="panel-state error">
      <p>{props.label}</p>
      <button type="button" className="secondary-action" onClick={props.onRetry}>
        重试
      </button>
    </div>
  )
}

function EmptyPanel(props: { title: string; description: string }) {
  return (
    <div className="panel-state empty">
      <strong>{props.title}</strong>
      <p>{props.description}</p>
    </div>
  )
}

async function fetchCount(
  client: ReturnType<typeof useAuth>['client'],
  query: NoticeQuery,
  overrides: Partial<NoticeQuery>,
  signal: AbortSignal,
) {
  const data = await client.get<PageData<NoticeItem>>('/v1/notices', {
    signal,
    query: buildListQuery({ ...query, ...overrides }, 1, 1),
  })
  return data.total
}

function buildListQuery(query: NoticeQuery, page: number, customPageSize = pageSize) {
  return {
    page,
    page_size: customPageSize,
    keyword: query.keyword,
    month: query.month,
    category: query.category,
    review_status: query.reviewStatus,
    archived: query.archived,
    captured_today: query.capturedToday,
    source_site: query.sourceSite,
    keyword_hit: query.keywordHit,
    high_priority: query.highPriority,
    high_quality: query.highQuality,
    project_signal: query.projectSignal,
  }
}

function buildMonthQuery(query: NoticeQuery) {
  const { page: _page, page_size: _pageSize, month: _month, ...filters } = buildListQuery(
    query,
    1,
  )
  return filters
}

function replaceQuery(
  navigate: ReturnType<typeof useNavigate>,
  query: NoticeQuery,
  patch: Partial<NoticeQuery>,
) {
  const nextQuery: NoticeQuery = {
    keyword: 'keyword' in patch ? patch.keyword : query.keyword,
    month: 'month' in patch ? patch.month : query.month,
    category: 'category' in patch ? patch.category : query.category,
    reviewStatus: 'reviewStatus' in patch ? patch.reviewStatus : query.reviewStatus,
    archived: 'archived' in patch ? patch.archived : query.archived,
    capturedToday: 'capturedToday' in patch ? patch.capturedToday : query.capturedToday,
    sourceSite: 'sourceSite' in patch ? patch.sourceSite : query.sourceSite,
    keywordHit: 'keywordHit' in patch ? patch.keywordHit : query.keywordHit,
    highPriority: 'highPriority' in patch ? patch.highPriority : query.highPriority,
    highQuality: 'highQuality' in patch ? patch.highQuality : query.highQuality,
    projectSignal: 'projectSignal' in patch ? patch.projectSignal : query.projectSignal,
    noticeId: 'noticeId' in patch ? patch.noticeId : query.noticeId,
  }
  navigate(buildNoticeUrl(sanitizeQuery(nextQuery)), { replace: true })
}

function sanitizeQuery(query: NoticeQuery): NoticeQuery {
  return Object.fromEntries(
    Object.entries(query).filter(([, value]) => value !== undefined && value !== ''),
  ) as NoticeQuery
}

function buildActiveFilters(query: NoticeQuery, sourceNameMap: Map<string, string>) {
  const filters: Array<{ key: keyof NoticeQuery; label: string }> = []
  if (query.keyword) filters.push({ key: 'keyword', label: `关键词: ${query.keyword}` })
  if (query.month) filters.push({ key: 'month', label: `月份: ${formatMonthLabel(query.month)}` })
  if (query.category) filters.push({ key: 'category', label: `类别: ${query.category}` })
  if (query.projectSignal) filters.push({ key: 'projectSignal', label: `类型: ${query.projectSignal}` })
  if (query.reviewStatus) filters.push({ key: 'reviewStatus', label: `状态: ${query.reviewStatus}` })
  if (query.sourceSite) filters.push({ key: 'sourceSite', label: `来源: ${sourceNameMap.get(query.sourceSite) ?? query.sourceSite}` })
  if (query.capturedToday) filters.push({ key: 'capturedToday', label: '仅今日采集' })
  if (query.archived) filters.push({ key: 'archived', label: '仅已归档' })
  if (query.highPriority) filters.push({ key: 'highPriority', label: '高优先级' })
  if (query.keywordHit) filters.push({ key: 'keywordHit', label: '关键词命中' })
  return filters
}

function formatDate(value: string | null) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatFullDate(value: string | null) {
  if (!value) return '原网站未提供'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatMonthLabel(value: string) {
  const [year, month] = value.split('-')
  return `${year}年${Number(month)}月`
}

function toErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}

type LoadState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: string }

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { PropsWithChildren } from 'react'
import { DashboardPage } from './DashboardPage'

const navigate = vi.fn()
const clientGet = vi.fn()
const clientPost = vi.fn()

vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({
    status: 'authenticated' as const,
    session: {
      user: { role: 'admin' as const },
    },
    client: {
      get: clientGet,
      post: clientPost,
    },
  }),
}))

vi.mock('../../app/router', async () => {
  const actual = await vi.importActual<typeof import('../../app/router')>('../../app/router')
  return {
    ...actual,
    useNavigate: () => navigate,
  }
})

describe('DashboardPage', () => {
  beforeEach(() => {
    navigate.mockReset()
    clientGet.mockReset()
    clientPost.mockReset()
    clientPost.mockResolvedValue({ task_id: 1, status: 'queued' })
  })

  it('renders overview and wires dashboard interactions to notice routes', async () => {
    clientGet.mockResolvedValue(createOverview())
    const user = userEvent.setup()

    renderWithClient(<DashboardPage />)

    expect(screen.getByText('正在加载首页看板…')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '今日监测概览' })).toBeInTheDocument()
    expect(screen.getByText('数据库 正常')).toBeInTheDocument()
    expect(screen.getByText('调度 正常 · 6 项')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '看板内容' })).toHaveAttribute('data-scroll-region', 'content')
    expect(screen.queryByText('进入今日采集结果，直接看当日新增。')).not.toBeInTheDocument()
    expect(screen.queryByText('查看项目申报、指南、征集类线索。')).not.toBeInTheDocument()
    expect(screen.getAllByText('国家药监局项目申报通知')).toHaveLength(2)
    expect(screen.getByText('采集完整度 95')).toHaveAttribute(
      'title',
      '采集完整度：根据标题、正文长度、乱码和结构完整性计算，不代表公告重要性',
    )
    expect(screen.queryByText('bulk.example')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /今日发布公告/i }))
    expect(navigate).toHaveBeenCalledWith('/notices?business_today=true')

    await user.click(screen.getByRole('button', { name: '申报通知 5' }))
    expect(navigate).toHaveBeenCalledWith('/notices?project_signal=%E7%94%B3%E6%8A%A5%E9%80%9A%E7%9F%A5')

    await user.click(screen.getByRole('button', { name: '结果公示 3' }))
    expect(navigate).toHaveBeenCalledWith('/notices?project_signal=%E7%BB%93%E6%9E%9C%E5%85%AC%E7%A4%BA')

    await user.click(screen.getByRole('button', { name: '国家药监局项目申报通知 5 条' }))
    expect(navigate).toHaveBeenCalledWith('/notices?source_site=nmpa.example')

    await user.click(screen.getByRole('button', { name: '医药 12' }))
    expect(navigate).toHaveBeenCalledWith('/notices?keyword=%E5%8C%BB%E8%8D%AF')

    await user.click(screen.getByRole('button', { name: '结果公示 3 条' }))
    expect(navigate).toHaveBeenCalledWith('/notices?project_signal=%E7%BB%93%E6%9E%9C%E5%85%AC%E7%A4%BA')

    await user.click(screen.getByRole('button', { name: '创新药项目申报通知 打开公告详情' }))
    expect(navigate).toHaveBeenCalledWith('/notices?notice_id=101')

    await user.click(screen.getByRole('button', { name: '最新系统提醒 打开公告详情' }))
    expect(navigate).toHaveBeenCalledWith('/notices?notice_id=201')
  })

  it('shows a recoverable error state and retries the query', async () => {
    clientGet
      .mockRejectedValueOnce(new Error('dashboard failed'))
      .mockResolvedValueOnce(createOverview({ metrics: { today_new_notices: 18 } }))
    const user = userEvent.setup()

    renderWithClient(<DashboardPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('首页看板加载失败')
    await user.click(screen.getByRole('button', { name: '重试' }))

    await waitFor(() => {
      expect(screen.getByText('18')).toBeInTheDocument()
    })
  })

  it('shows an empty state when no operational data is available', async () => {
    clientGet.mockResolvedValue(
      createOverview({
        metrics: {
          today_new_notices: 0,
          keyword_hit_notices: 0,
          monitoring_site_count: 0,
          high_priority_notices: 0,
          high_quality_notices: 0,
          project_declaration_notices: 0,
          result_publication_notices: 0,
        },
        high_value_notices: [],
        recent_notices: [],
        keyword_heat: [],
        source_distribution: [],
        project_signal_distribution: [],
      }),
    )

    renderWithClient(<DashboardPage />)

    expect(await screen.findByText('暂无可展示的公告与监测统计')).toBeInTheDocument()
  })

  it('shows collection freshness and failed source warning', async () => {
    clientGet.mockResolvedValue(
      createOverview({
        collection_health: {
          status: 'error',
          monitored_task_count: 7,
          failed_task_count: 7,
          partial_task_count: 0,
          stale_task_count: 7,
          last_success_at: '2026-08-04T06:00:00Z',
          failed_sources: ['科技部项目申报采集', '广东省科技厅项目申报采集'],
          partial_sources: [],
          issues: [
            {
              task_id: 1,
              task_name: '科技部项目申报采集',
              status: 'failed',
              reason: '目标网站拒绝访问（HTTP 403）',
              is_stale: true,
              last_success_at: '2026-08-04T06:00:00Z',
            },
          ],
        },
      }),
    )

    const user = userEvent.setup()

    renderWithClient(<DashboardPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('采集数据已过期')
    expect(alert).toHaveTextContent('7 个来源最近运行失败')
    expect(alert).toHaveTextContent('7 个来源超过 24 小时未成功更新')
    expect(alert).toHaveTextContent('数据截至 2026/08/04 14:00')
    expect(alert).not.toHaveTextContent('科技部项目申报采集')
    expect(alert).not.toHaveTextContent('目标网站拒绝访问（HTTP 403）')
    expect(screen.queryByRole('button', { name: '重新运行 科技部项目申报采集' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '查看 1 个异常' }))

    const drawer = screen.getByRole('dialog', { name: '采集异常详情' })
    expect(drawer).toHaveTextContent('科技部项目申报采集')
    expect(drawer).toHaveTextContent('目标网站拒绝访问（HTTP 403）')

    await user.click(within(drawer).getByRole('button', { name: '重新运行 科技部项目申报采集' }))
    expect(clientPost).toHaveBeenCalledWith('/v1/tasks/1/run')
    expect(await screen.findByRole('status')).toHaveTextContent('科技部项目申报采集已提交重跑')
  })

  it('updates every enabled source from the collection warning with one click', async () => {
    const bulkRun = createDeferred<{
      queued_task_ids: number[]
      skipped_task_ids: number[]
      recovered_task_ids: number[]
      quarantined_task_ids: number[]
      errors: string[]
    }>()
    clientGet.mockResolvedValue(
      createOverview({
        collection_health: {
          status: 'warning',
          monitored_task_count: 7,
          failed_task_count: 1,
          partial_task_count: 0,
          stale_task_count: 1,
          last_success_at: '2026-08-04T06:00:00Z',
          failed_sources: ['科技部项目申报采集'],
          partial_sources: [],
          issues: [
            {
              task_id: 1,
              task_name: '科技部项目申报采集',
              status: 'failed',
              reason: '目标网站请求超时',
              is_stale: true,
              last_success_at: '2026-08-04T06:00:00Z',
            },
          ],
        },
      }),
    )
    clientPost.mockReturnValueOnce(bulkRun.promise)
    const user = userEvent.setup()

    renderWithClient(<DashboardPage />)

    const bulkButton = await screen.findByRole('button', { name: '更新全部来源' })
    await user.click(bulkButton)
    await user.click(bulkButton)

    expect(clientPost).toHaveBeenCalledTimes(1)
    expect(clientPost).toHaveBeenCalledWith('/v1/tasks/run-enabled')
    expect(bulkButton).toBeDisabled()
    expect(bulkButton).toHaveTextContent('正在更新')

    bulkRun.resolve({
      queued_task_ids: [1, 2, 3, 4, 5],
      skipped_task_ids: [6, 7],
      recovered_task_ids: [],
      quarantined_task_ids: [],
      errors: [],
    })

    expect(await screen.findByRole('status')).toHaveTextContent('已提交 5 个来源，2 个正在运行的来源已跳过')
  })

  it('shows a partial collection warning even when the latest run stored data', async () => {
    clientGet.mockResolvedValue(
      createOverview({
        collection_health: {
          status: 'warning',
          monitored_task_count: 7,
          failed_task_count: 0,
          partial_task_count: 1,
          stale_task_count: 0,
          last_success_at: '2026-08-07T01:15:16Z',
          failed_sources: [],
          partial_sources: ['广东省科技厅项目申报与结果公示采集'],
          issues: [
            {
              task_id: 2,
              task_name: '广东省科技厅项目申报与结果公示采集',
              status: 'partial',
              reason: '列表跟进本次有 2 条处理失败；最近原因：请求超时。',
              is_stale: false,
              last_success_at: '2026-08-07T01:15:16Z',
            },
          ],
        },
      }),
    )

    const user = userEvent.setup()

    renderWithClient(<DashboardPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('采集运行异常')
    expect(alert).toHaveTextContent('1 个来源本次部分失败')
    expect(alert).not.toHaveTextContent('列表跟进本次有 2 条处理失败；最近原因：请求超时。')

    await user.click(screen.getByRole('button', { name: '查看 1 个异常' }))
    expect(screen.getByRole('dialog', { name: '采集异常详情' })).toHaveTextContent(
      '列表跟进本次有 2 条处理失败；最近原因：请求超时。',
    )
  })
})

function renderWithClient(node: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }

  return render(node, { wrapper: Wrapper })
}

function createOverview(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    metrics: {
      today_new_notices: 24,
      keyword_hit_notices: 12,
      monitoring_site_count: 9,
      high_priority_notices: 4,
      high_quality_notices: 2,
      project_declaration_notices: 5,
      result_publication_notices: 3,
      ...(overrides.metrics as Record<string, number> | undefined),
    },
    runtime: {
      status: 'ok',
      database: 'ok',
      scheduler: 'ok',
      scheduled_jobs: 6,
    },
    collection_health: {
      status: 'healthy',
      monitored_task_count: 9,
      failed_task_count: 0,
      partial_task_count: 0,
      stale_task_count: 0,
      last_success_at: '2026-08-03T09:30:00Z',
      failed_sources: [],
      partial_sources: [],
      issues: [],
    },
    high_value_notices: [
      {
        id: 101,
        title: '创新药项目申报通知',
        summary: '聚焦创新药重大专项。',
        source_site: 'nmpa.example',
        source_url: 'https://nmpa.example/high-value',
        published_at: '2026-08-03T08:00:00Z',
        captured_at: '2026-08-03T08:10:00Z',
        quality_score: 95,
        matched_keywords: ['创新药'],
        is_high_priority: true,
        category: '项目申报',
        ai_summary: null,
        review_status: '待关注',
        is_archived: false,
        remark: null,
        task_id: 11,
      },
    ],
    recent_notices: [
      {
        id: 201,
        title: '最新系统提醒',
        summary: '最近一条公告。',
        source_site: 'bulk.example',
        source_url: 'https://bulk.example/latest',
        published_at: '2026-08-03T09:00:00Z',
        captured_at: '2026-08-03T09:02:00Z',
        quality_score: 50,
        matched_keywords: [],
        is_high_priority: false,
        category: '未分类',
        ai_summary: null,
        review_status: '待关注',
        is_archived: false,
        remark: null,
        task_id: 22,
      },
    ],
    keyword_heat: [
      { keyword: '医药', count: 12 },
      { keyword: '创新药', count: 4 },
    ],
    source_distribution: [
      {
        source_site: 'nmpa.example',
        display_name: '国家药监局项目申报通知',
        notice_count: 5,
        percentage: 55.6,
      },
    ],
    project_signal_distribution: [
      {
        label: '结果公示',
        notice_count: 3,
        percentage: 33.3,
      },
    ],
    last_updated_at: '2026-08-03T09:30:00Z',
    ...overrides,
  }
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

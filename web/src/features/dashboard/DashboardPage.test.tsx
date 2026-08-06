import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { PropsWithChildren } from 'react'
import { DashboardPage } from './DashboardPage'

const navigate = vi.fn()
const clientGet = vi.fn()

vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({
    status: 'authenticated' as const,
    client: {
      get: clientGet,
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
    expect(screen.queryByText('bulk.example')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /今日新增公告/i }))
    expect(navigate).toHaveBeenCalledWith('/notices?captured_today=true')

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

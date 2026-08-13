import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiClient } from '../../api/client'
import { AuthProvider } from '../../auth/AuthProvider'
import { NoticesPage } from './NoticesPage'

interface MockFetchOptions {
  notices?: NoticeRecord[]
  detail?: NoticeDetailRecord
  months?: Array<{ month: string; count: number }>
  monthFailures?: number
}

interface NoticeRecord {
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
  is_focused?: boolean
  remark: string | null
  task_id: number
}

interface NoticeDetailRecord extends NoticeRecord {
  content_text: string
  content_html: string
  content_hash: string | null
  snapshot_path: string | null
  metadata: Record<string, unknown> | null
}

const baseNotices: NoticeRecord[] = [
  {
    id: 101,
    title: '2026年创新药项目申报通知',
    summary: '面向重点创新药方向的项目申报通知。',
    source_site: 'nmpa',
    source_url: 'https://example.com/nmpa/101',
    published_at: '2026-08-01T09:00:00+08:00',
    captured_at: '2026-08-03T08:00:00+08:00',
    quality_score: 95,
    matched_keywords: ['创新药', '申报'],
    is_high_priority: true,
    project_signal: '申报通知',
    category: '项目申报通知',
    ai_summary: '创新药申报窗口已开启。',
    review_status: '待关注',
    is_archived: false,
    remark: null,
    task_id: 5,
  },
  {
    id: 202,
    title: 'xanthine oxidoreductase 最新竞品研究',
    summary: 'PubMed 最新竞品文献。',
    source_site: 'pubmed',
    source_url: 'https://example.com/pubmed/202',
    published_at: '2026-08-02T10:30:00+08:00',
    captured_at: '2026-08-03T09:30:00+08:00',
    quality_score: 82,
    matched_keywords: ['xanthine', 'oxidoreductase'],
    is_high_priority: false,
    project_signal: '其他项目线索',
    category: '竞品文献',
    ai_summary: '涉及靶点活性与临床对比。',
    review_status: '已跟进',
    is_archived: false,
    remark: '需要转研发团队',
    task_id: 6,
  },
]

const baseDetail: NoticeDetailRecord = {
  ...baseNotices[0],
  content_text: '正文包含创新药和申报两个关键词，适合测试快照高亮。',
  content_html: '<p>正文包含创新药和申报两个关键词。</p>',
  content_hash: null,
  snapshot_path: '/snapshots/101.txt',
  metadata: {
    kind: 'government_notice',
  },
}

const julyNotice: NoticeRecord = {
  ...baseNotices[0],
  id: 303,
  title: '缺少发布日期的七月公告',
  source_url: 'https://example.com/nmpa/303',
  published_at: null,
  captured_at: '2026-07-18T08:00:00+08:00',
}

describe('NoticesPage', () => {
  it('renders source display names and loads selected detail', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices?source_site=pubmed&notice_id=202')
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })

    renderWithProviders(fetcher)

    const collapsedFilterToggle = await screen.findByRole('button', { expanded: false })
    await userEvent.click(collapsedFilterToggle)

    expect(await screen.findByRole('heading', { name: '筛选与处理' })).toBeInTheDocument()
    expect(screen.queryByText('清空高优先级和命中过滤')).not.toBeInTheDocument()
    expect(screen.queryByText('只看业务高优先级')).not.toBeInTheDocument()
    expect(await screen.findByRole('option', { name: 'PubMed 竞品文献' })).toBeInTheDocument()
    expect(await screen.findByRole('article', { name: /xanthine oxidoreductase 最新竞品研究/i })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '公告结果' })).toHaveAttribute('data-scroll-region', 'list')
    const detailPanel = await screen.findByRole('region', { name: '公告详情' })
    expect(within(detailPanel).getByRole('heading', { name: 'xanthine oxidoreductase 最新竞品研究' })).toBeInTheDocument()
    expect(within(detailPanel).getByText('采集完整度 82')).toHaveAttribute(
      'title',
      '采集完整度：根据标题、正文长度、乱码和结构完整性计算，不代表公告重要性',
    )
    const originalLink = within(detailPanel).getByRole('link', { name: '查看原文' })
    const snapshotButton = within(detailPanel).getByRole('button', { name: '查看采集快照' })
    expect(originalLink).toHaveClass('primary-action', 'notice-original-action')
    expect(originalLink).toHaveAttribute('target', '_blank')
    expect(snapshotButton).toHaveClass('secondary-action', 'notice-snapshot-action')
    expect(originalLink.compareDocumentPosition(snapshotButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('syncs filters to the url and allows source or keyword drilling', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    const highPriorityCard = await screen.findByRole('button', { name: /高优先级公告/i })
    await userEvent.click(highPriorityCard)
    await waitFor(() => {
      expect(window.location.search).toContain('high_priority=true')
    })

    const sourceChip = (await screen.findAllByRole('button', { name: /来源 国家药监局/i }))[0]
    await userEvent.click(sourceChip)
    await waitFor(() => {
      expect(window.location.search).toContain('source_site=nmpa')
    })

    const projectSignalChip = (await screen.findAllByRole('button', { name: '申报通知' }))[0]
    await userEvent.click(projectSignalChip)
    await waitFor(() => {
      expect(window.location.search).toContain(
        'project_signal=%E7%94%B3%E6%8A%A5%E9%80%9A%E7%9F%A5',
      )
    })

    await userEvent.click(screen.getByRole('button', { name: /2026年创新药项目申报通知/ }))
    const detailKeyword = await screen.findByRole('button', { name: /关键词 创新药/i })
    await userEvent.click(detailKeyword)
    await waitFor(() => {
      expect(window.location.search).toContain('keyword=%E5%88%9B%E6%96%B0%E8%8D%AF')
    })
  })

  it('filters requirement 1 notices by information type', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    await userEvent.click(await screen.findByRole('button', { expanded: false }))
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: '信息类型' }),
      '结果公示',
    )

    await waitFor(() => {
      expect(window.location.search).toContain(
        'project_signal=%E7%BB%93%E6%9E%9C%E5%85%AC%E7%A4%BA',
      )
    })
    expect(screen.getByText('类型: 结果公示')).toBeInTheDocument()
  })

  it('filters by business month and keeps the today shortcut mutually exclusive', async () => {
    const fetcher = createMockFetcher({ notices: [...baseNotices, julyNotice] })
    window.history.replaceState(null, '', '/notices?captured_today=true')

    renderWithProviders(fetcher)

    await userEvent.click(await screen.findByRole('button', { name: /2026年7月.*1/ }))
    await waitFor(() => {
      expect(window.location.search).toContain('month=2026-07')
      expect(window.location.search).not.toContain('captured_today')
    })
    expect(await screen.findByText('月份: 2026年7月')).toBeInTheDocument()
    expect(await screen.findByText('采集日期')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { expanded: false }))
    await userEvent.click(screen.getByRole('button', { name: '仅今日采集' }))
    await waitFor(() => {
      expect(window.location.search).toContain('captured_today=true')
      expect(window.location.search).not.toContain('month=')
    })
  })

  it('offers a persistent shortcut for notices published today with keyword matches', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices?month=2026-08')

    renderWithProviders(fetcher)

    const shortcut = await screen.findByRole('button', { name: '今日发布命中' })
    expect(shortcut).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(shortcut)
    await waitFor(() => {
      expect(window.location.search).toContain('business_today=true')
      expect(window.location.search).toContain('keyword_hit=true')
      expect(window.location.search).not.toContain('captured_today')
      expect(window.location.search).not.toContain('month=')
    })
    expect(shortcut).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(shortcut)
    await waitFor(() => {
      expect(window.location.search).not.toContain('business_today')
      expect(window.location.search).not.toContain('keyword_hit')
    })
    expect(shortcut).toHaveAttribute('aria-pressed', 'false')
  })

  it('filters notices published this week and clears conflicting date filters', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(
      null,
      '',
      '/notices?month=2026-08&captured_today=true&business_today=true',
    )

    renderWithProviders(fetcher)

    const shortcut = await screen.findByRole('button', { name: '本周发布' })
    expect(shortcut).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(shortcut)
    await waitFor(() => {
      expect(window.location.search).toContain('business_week=true')
      expect(window.location.search).not.toContain('business_today')
      expect(window.location.search).not.toContain('captured_today')
      expect(window.location.search).not.toContain('month=')
    })
    expect(shortcut).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findAllByText('本周发布')).toHaveLength(2)
    expect(screen.getByRole('button', { name: /全部月份/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )

    await userEvent.click(shortcut)
    await waitFor(() => {
      expect(window.location.search).not.toContain('business_week')
    })
    expect(shortcut).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows the full publication year and omits meaningless midnight time on cards', async () => {
    const historicalNotice: NoticeRecord = {
      ...baseNotices[0],
      id: 404,
      title: '2023年历史项目申报通知',
      source_url: 'https://example.com/nmpa/404',
      published_at: '2023-08-22T00:00:00+08:00',
      captured_at: '2026-08-07T09:15:00+08:00',
    }
    const fetcher = createMockFetcher({ notices: [historicalNotice, baseNotices[0]] })
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    const card = await screen.findByRole('article', { name: /2023年历史项目申报通知/ })
    expect(within(card).getByText('2023/08/22')).toBeInTheDocument()
    expect(within(card).getByText('历史补采')).toBeInTheDocument()
    expect(within(card).queryByText(/08\/22 00:00/)).not.toBeInTheDocument()

    const regularCard = await screen.findByRole('article', { name: /2026年创新药项目申报通知/ })
    expect(within(regularCard).queryByText('历史补采')).not.toBeInTheDocument()
  })

  it('jumps directly to a requested page and clamps out-of-range values', async () => {
    const notices = Array.from({ length: 45 }, (_, index) => ({
      ...baseNotices[index % baseNotices.length],
      id: index + 1,
      title: `分页公告 ${index + 1}`,
      source_url: `https://example.com/notices/${index + 1}`,
    }))
    const fetcher = createMockFetcher({ notices })
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    const pageInput = await screen.findByRole('spinbutton', { name: '跳转页码' })
    await userEvent.clear(pageInput)
    await userEvent.type(pageInput, '3')
    await userEvent.click(screen.getByRole('button', { name: '前往指定页' }))

    expect(await screen.findByText('分页公告 41')).toBeInTheDocument()
    expect(await screen.findByRole('spinbutton', { name: '跳转页码' })).toHaveValue(3)
    expect(screen.getByText('/ 3 页')).toBeInTheDocument()

    const currentPageInput = await screen.findByRole('spinbutton', { name: '跳转页码' })
    await userEvent.clear(currentPageInput)
    await userEvent.type(currentPageInput, '99')
    await userEvent.click(screen.getByRole('button', { name: '前往指定页' }))

    await waitFor(() => {
      expect(screen.getByRole('spinbutton', { name: '跳转页码' })).toHaveValue(3)
    })
    expect(fetcher.calls.listPages).toContain(3)
  })

  it('keeps older months available without increasing the page height', async () => {
    const fetcher = createMockFetcher({
      months: [
        { month: '2026-08', count: 2 },
        { month: '2026-07', count: 1 },
        { month: '2026-06', count: 4 },
        { month: '2026-05', count: 3 },
        { month: '2026-04', count: 2 },
        { month: '2025-12', count: 1 },
      ],
    })
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    const olderMonths = await screen.findByRole('combobox', { name: '更多月份' })
    await userEvent.selectOptions(olderMonths, '2025-12')
    await waitFor(() => {
      expect(window.location.search).toContain('month=2025-12')
    })
  })

  it('shows both publication and capture timestamps in the detail drawer', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices?notice_id=101')

    renderWithProviders(fetcher)

    const detailPanel = await screen.findByRole('region', { name: '公告详情' })
    expect(within(detailPanel).getByText('发布日期')).toBeInTheDocument()
    expect(within(detailPanel).getByText('采集时间')).toBeInTheDocument()
  })

  it('marks a notice as important from the card without opening its detail', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    const noticeCard = await screen.findByRole('article', {
      name: /2026年创新药项目申报通知/,
    })
    await userEvent.click(within(noticeCard).getByRole('button', { name: '标记重点关注' }))

    await waitFor(() => {
      expect(fetcher.calls.patchReview.at(-1)?.body).toMatchObject({ review_status: '重点关注' })
    })
    expect(window.location.search).not.toContain('notice_id=')
  })

  it('filters notices by important status from the persistent quick filter', async () => {
    const fetcher = createMockFetcher({
      notices: [
        baseNotices[0],
        { ...baseNotices[1], review_status: '重点关注' },
      ],
    })
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    await userEvent.click(await screen.findByRole('button', { name: '只看重点关注' }))

    await waitFor(() => {
      expect(window.location.search).toContain('review_status=%E9%87%8D%E7%82%B9%E5%85%B3%E6%B3%A8')
    })
    expect(await screen.findByRole('article', { name: /xanthine oxidoreductase/ })).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: /2026年创新药项目申报通知/ })).not.toBeInTheDocument()
  })

  it('removes important status from the detail drawer', async () => {
    const focusedDetail = { ...baseDetail, review_status: '重点关注' }
    const fetcher = createMockFetcher({
      notices: [{ ...baseNotices[0], review_status: '重点关注' }],
      detail: focusedDetail,
    })
    window.history.replaceState(
      null,
      '',
      '/notices?review_status=%E9%87%8D%E7%82%B9%E5%85%B3%E6%B3%A8&notice_id=101',
    )

    renderWithProviders(fetcher)

    const detailPanel = await screen.findByRole('region', { name: '公告详情' })
    await userEvent.click(within(detailPanel).getByRole('button', { name: '取消重点关注' }))

    await waitFor(() => {
      expect(fetcher.calls.patchReview.at(-1)?.body).toMatchObject({ review_status: '待关注' })
    })
    expect(await screen.findByText('没有符合条件的公告')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /全部公告\s*0/ })).toBeInTheDocument()
    expect(screen.getByText('已取消重点关注')).toBeInTheDocument()
  })

  it('retries month loading without blocking the notice list', async () => {
    const fetcher = createMockFetcher({ monthFailures: 1 })
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher)

    expect(await screen.findByRole('article', { name: /2026年创新药项目申报通知/ })).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: '月份加载失败，点击重试' }))

    expect(await screen.findByRole('button', { name: /2026年8月.*2/ })).toBeInTheDocument()
    expect(fetcher.calls.monthLoads).toBe(2)
  })

  it('prevents duplicate review actions and shows snapshot content', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices?notice_id=101')
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(fetcher)

    const archiveButton = await screen.findByRole('button', { name: /归档公告/i })
    await userEvent.click(archiveButton)
    expect(archiveButton).toBeDisabled()

    await waitFor(() => {
      expect(fetcher.calls.patchReview).toHaveLength(1)
    })

    const snapshotButton = await screen.findByRole('button', { name: /查看采集快照/i })
    await userEvent.click(snapshotButton)

    const dialog = await screen.findByRole('dialog', { name: '采集快照' })
    expect(within(dialog).getByText(/适合测试快照高亮/)).toBeInTheDocument()

    confirmSpy.mockRestore()
  })

  it('keeps review and archive actions read-only for a regular user', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices?notice_id=101')

    renderWithProviders(fetcher, false)

    expect(await screen.findByRole('region', { name: '公告详情' })).toBeInTheDocument()
    expect(screen.getByText(/普通用户可查看详情，但不能修改跟进状态或归档/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /归档公告/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '已跟进' })).not.toBeInTheDocument()
  })

  it('lets a regular user keep a personal focus without changing review status', async () => {
    const fetcher = createMockFetcher()
    window.history.replaceState(null, '', '/notices')

    renderWithProviders(fetcher, false)

    const noticeCard = await screen.findByRole('article', {
      name: /2026年创新药项目申报通知/,
    })
    await userEvent.click(within(noticeCard).getByRole('button', { name: '加入我的关注' }))

    await waitFor(() => expect(fetcher.calls.personalFocus).toEqual(['PUT']))
    expect(fetcher.calls.patchReview).toHaveLength(0)
    expect(await screen.findByText('已加入我的关注')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '只看我的关注' }))
    await waitFor(() => expect(window.location.search).toContain('focused_only=true'))
  })
})

function renderWithProviders(fetcher: typeof fetch, canManage = true) {
  const client = new ApiClient({ fetcher })

  render(
    <AuthProvider clientFactory={() => client}>
      <NoticesPage canManage={canManage} />
    </AuthProvider>,
  )
}

function createMockFetcher(options: MockFetchOptions = {}) {
  let notices = [...(options.notices ?? baseNotices)]
  const months = options.months ?? [
    { month: '2026-08', count: 2 },
    { month: '2026-07', count: notices.some((item) => item.id === 303) ? 1 : 0 },
  ]
  let detail = options.detail ?? {
    ...baseDetail,
    ...(baseNotices.find((item) => item.id === 101) ?? {}),
  }
  const calls = {
    patchReview: [] as Array<{ noticeId: number; body: unknown }>,
    monthLoads: 0,
    listPages: [] as number[],
    personalFocus: [] as string[],
  }

  const fetcher: typeof fetch & { calls: typeof calls } = Object.assign(
    async (input: string | URL | Request, init?: RequestInit) => {
      const rawUrl =
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const url = new URL(rawUrl, 'http://localhost')
      const path = url.pathname
      const pageSize = Number(url.searchParams.get('page_size') ?? '20')
      const page = Number(url.searchParams.get('page') ?? '1')
      const highPriority = readBool(url.searchParams.get('high_priority'))
      const keywordHit = readBool(url.searchParams.get('keyword_hit'))
      const keyword = url.searchParams.get('keyword')
      const sourceSite = url.searchParams.get('source_site')
      const month = url.searchParams.get('month')
      const reviewStatus = url.searchParams.get('review_status')
      const focusedOnly = readBool(url.searchParams.get('focused_only'))

      if (path === '/v1/notices/source-sites') {
        return jsonResponse([
          { source_site: 'nmpa', display_name: '国家药监局' },
          { source_site: 'pubmed', display_name: 'PubMed 竞品文献' },
        ])
      }

      if (path === '/v1/notices/months') {
        calls.monthLoads += 1
        if (calls.monthLoads <= (options.monthFailures ?? 0)) {
          return apiErrorResponse('月份暂时不可用')
        }
        return jsonResponse(months.filter((item) => item.count > 0))
      }

      if (path === '/v1/notices' && pageSize === 1) {
        const total = notices.filter((item) => {
          if (highPriority === true && !item.is_high_priority) return false
          if (keywordHit === true && item.matched_keywords.length === 0) return false
          if (sourceSite && item.source_site !== sourceSite) return false
          if (keyword && !`${item.title} ${item.summary}`.includes(keyword)) return false
          if (month && businessMonth(item) !== month) return false
          if (reviewStatus && item.review_status !== reviewStatus) return false
          if (focusedOnly === true && item.is_focused !== true) return false
          return true
        }).length
        return jsonResponse({ items: notices.slice(0, 1), total, page: 1, page_size: 1 })
      }

      if (path === '/v1/notices') {
        const filtered = notices.filter((item) => {
          if (highPriority === true && !item.is_high_priority) return false
          if (keywordHit === true && item.matched_keywords.length === 0) return false
          if (sourceSite && item.source_site !== sourceSite) return false
          if (keyword && !`${item.title} ${item.summary}`.includes(keyword)) return false
          if (month && businessMonth(item) !== month) return false
          if (reviewStatus && item.review_status !== reviewStatus) return false
          if (focusedOnly === true && item.is_focused !== true) return false
          return true
        })
        calls.listPages.push(page)
        const start = (page - 1) * pageSize
        return jsonResponse({
          items: filtered.slice(start, start + pageSize),
          total: filtered.length,
          page,
          page_size: pageSize,
        })
      }

      if (path === '/v1/notices/101') {
        return jsonResponse(detail)
      }

      if (path === '/v1/notices/202') {
        return jsonResponse({
          ...baseNotices[1],
          content_text: 'PubMed 文献详情',
          content_html: '<p>PubMed 文献详情</p>',
          content_hash: null,
          snapshot_path: '/snapshots/202.txt',
          metadata: null,
        })
      }

      if (path === '/v1/notices/101/review') {
        const body = init?.body ? JSON.parse(String(init.body)) : {}
        calls.patchReview.push({
          noticeId: 101,
          body,
        })
        detail = {
          ...detail,
          review_status: body.review_status ?? detail.review_status,
          is_archived: body.is_archived ?? detail.is_archived,
          remark: body.remark ?? detail.remark,
        }
        notices = notices.map((item) =>
          item.id === 101
            ? {
                ...item,
                review_status: detail.review_status,
                is_archived: detail.is_archived,
                remark: detail.remark,
              }
            : item,
        )
        return delayedJsonResponse(detail)
      }

      if (path === '/v1/notices/101/focus') {
        const focused = init?.method === 'PUT'
        calls.personalFocus.push(init?.method ?? 'GET')
        detail = { ...detail, is_focused: focused }
        notices = notices.map((item) =>
          item.id === 101 ? { ...item, is_focused: focused } : item,
        )
        return delayedJsonResponse(detail)
      }

      if (path === '/v1/notices/101/snapshot') {
        return jsonResponse({
          id: 101,
          source_url: detail.source_url,
          source_site: detail.source_site,
          snapshot_path: '/snapshots/101.txt',
          content: detail.content_text,
        })
      }

      return new Response('not found', { status: 404 })
    },
    { calls },
  )

  return fetcher
}

function jsonResponse(data: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify({ code: 0, message: 'ok', data }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
      },
    }),
  )
}

function delayedJsonResponse(data: unknown, delayMs = 50) {
  return new Promise<Response>((resolve) => {
    window.setTimeout(() => {
      void jsonResponse(data).then(resolve)
    }, delayMs)
  })
}

function apiErrorResponse(message: string) {
  return Promise.resolve(
    new Response(JSON.stringify({ code: 1, message, data: null }), {
      status: 503,
      headers: {
        'Content-Type': 'application/json',
      },
    }),
  )
}

function readBool(value: string | null) {
  if (value === 'true') return true
  if (value === 'false') return false
  return undefined
}

function businessMonth(item: NoticeRecord) {
  return (item.published_at ?? item.captured_at ?? '').slice(0, 7)
}

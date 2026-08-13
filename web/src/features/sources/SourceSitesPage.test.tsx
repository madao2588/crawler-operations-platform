import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider } from '../../auth/AuthProvider'
import { ApiClient } from '../../api/client'
import { SourceSitesPage } from './SourceSitesPage'

describe('SourceSitesPage', () => {
  it('keeps source configuration read-only for a regular user', async () => {
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/templates/tasks' && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: [createTemplate({ id: 'gov', label: '省科技厅通知' })] })
      }
      if (url.startsWith('/v1/tasks') && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: { items: [], total: 0, page: 1, page_size: 100 } })
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })

    renderWithAuth(<SourceSitesPage canManage={false} />, fetcher)

    expect(await screen.findByText('省科技厅通知')).toBeInTheDocument()
    expect(screen.getByText(/普通用户为只读模式/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建模板' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /使用模板/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /编辑模板/ })).not.toBeInTheDocument()
  })

  it('supports source stats, tag filtering, template usage, manual collection, and retry states', async () => {
    const useGate = createDeferred<Response>()
    const templatesState = {
      current: [
        createTemplate({
          id: 'wechat_manual',
          label: '科创局公众号',
          name: 'wechat_manual_task',
          description: '人工登记公众号文章',
          tags: ['公众号', '政策'],
          parser_rules: '{"collection_mode":"manual"}',
        }),
        createTemplate({
          id: 'gov_auto',
          label: '省科技厅通知',
          name: 'gov_auto_task',
          description: '自动采集项目申报通知',
          tags: ['政策', '项目'],
          parser_rules: '{"list":"notice"}',
        }),
      ],
    }

    const onUseTemplate = vi.fn()
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/templates/tasks' && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: templatesState.current })
      }
      if (url.startsWith('/v1/tasks') && (!init || init.method === 'GET')) {
        return jsonResponse({
          code: 0,
          message: 'ok',
          data: {
            items: [
              createTask({
                id: 11,
                name: 'gov_auto_task',
                last_run_status: 'failed',
                last_error_message: 'selector parse failed',
              }),
            ],
            total: 1,
            page: 1,
            page_size: 100,
          },
        })
      }
      if (url.startsWith('/v1/logs?task_id=11') && (!init || init.method === 'GET')) {
        return jsonResponse({
          code: 0,
          message: 'ok',
          data: {
            items: [
              {
                id: 91,
                task_id: 11,
                level: 'error',
                message: 'selector parse failed',
                error_stack: 'selector parse failed',
                run_summary: null,
                created_at: '2026-08-03T10:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 1,
          },
        })
      }
      if (url === '/v1/templates/tasks/gov_auto/use' && init?.method === 'POST') {
        return useGate.promise
      }
      if (url === '/v1/templates/tasks/wechat_manual/collect' && init?.method === 'POST') {
        return jsonResponse({
          code: 0,
          message: 'ok',
          data: {
            source_id: 'wechat_manual',
            source_url: 'https://mp.weixin.qq.com/s/demo',
            status: 'stored',
            notice_id: 88,
          },
        })
      }
      if (url === '/v1/tasks/11/run' && init?.method === 'POST') {
        return jsonResponse({
          code: 0,
          message: 'ok',
          data: { task_id: 11, status: 'queued', recovered_stale_run: false },
        })
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })

    const user = userEvent.setup()
    renderWithAuth(<SourceSitesPage onUseTemplate={onUseTemplate} />, fetcher)

    expect(await screen.findByRole('heading', { name: '模板与运行状态' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '来源结果' })).toHaveAttribute('data-scroll-region', 'table')
    expect(screen.queryByText('统一筛选自动采集、人工登记和授权来源，点击表格行查看配置详情。')).not.toBeInTheDocument()
    expect(await screen.findByText('科创局公众号')).toBeInTheDocument()
    expect(screen.getByText('省科技厅通知')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /人工登记/ }))
    expect(screen.getByText('科创局公众号')).toBeInTheDocument()
    expect(screen.queryByText('省科技厅通知')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /全部模板/ }))
    await user.click(screen.getByRole('button', { name: '标签 政策' }))
    expect(screen.getByText('科创局公众号')).toBeInTheDocument()
    expect(screen.getByText('省科技厅通知')).toBeInTheDocument()

    const useButton = screen.getByRole('button', { name: '使用模板 省科技厅通知' })
    await user.click(useButton)
    expect(useButton).toBeDisabled()
    useGate.resolve(
      jsonResponse({
        code: 0,
        message: 'ok',
        data: { ...templatesState.current[1], usage_count: 2 },
      }),
    )
    await waitFor(() => expect(onUseTemplate).toHaveBeenCalledWith('gov_auto'))

    await user.click(screen.getByRole('button', { name: '登记文章 科创局公众号' }))
    const collectDialog = await screen.findByRole('dialog', { name: '登记公众号文章' })
    await user.type(within(collectDialog).getByLabelText('文章链接'), 'https://mp.weixin.qq.com/s/demo')
    await user.click(within(collectDialog).getByRole('button', { name: '登记入库' }))
    expect(await screen.findByRole('status')).toHaveTextContent('已登记到通知池 #88')

    await user.click(screen.getByRole('button', { name: '重试任务 省科技厅通知' }))
    expect(await screen.findByRole('status')).toHaveTextContent('已重新排队执行 省科技厅通知')
  })

  it('supports creating, testing, editing, and deleting templates', async () => {
    const templatesState = {
      current: [
        createTemplate({
          id: 'gov_auto',
          label: '省科技厅通知',
          name: 'gov_auto_task',
          description: '自动采集项目申报通知',
          tags: ['政策', '项目'],
          parser_rules: '{"list":"notice"}',
        }),
      ],
    }

    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/templates/tasks' && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: templatesState.current })
      }
      if (url.startsWith('/v1/tasks') && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: { items: [], total: 0, page: 1, page_size: 100 } })
      }
      if (url === '/v1/templates/test' && init?.method === 'POST') {
        return jsonResponse({
          code: 0,
          message: 'ok',
          data: {
            title: '测试抓取标题',
            content_text: '正文预览',
            content_html: '<p>正文预览</p>',
            quality_score: 82,
            error: null,
            trace: { fetch: 'ok', content_source: 'selector', notes: ['content extracted'] },
          },
        })
      }
      if (url === '/v1/templates/tasks' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        const created = createTemplate({ ...body, id: 'new_source', usage_count: 0, last_used_at: null })
        templatesState.current = [created, ...templatesState.current]
        return jsonResponse({ code: 0, message: 'ok', data: created })
      }
      if (url === '/v1/templates/tasks/gov_auto' && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body))
        templatesState.current = templatesState.current.map((template) =>
          template.id === 'gov_auto' ? { ...template, ...body } : template,
        )
        return jsonResponse({ code: 0, message: 'ok', data: templatesState.current.find((template) => template.id === 'gov_auto') })
      }
      if (url === '/v1/templates/tasks/gov_auto' && init?.method === 'DELETE') {
        templatesState.current = templatesState.current.filter((template) => template.id !== 'gov_auto')
        return jsonResponse({ code: 0, message: 'ok', data: {} })
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })

    const user = userEvent.setup()
    renderWithAuth(<SourceSitesPage />, fetcher)

    expect(await screen.findByText('省科技厅通知')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '新建模板' }))
    const createDialog = await screen.findByRole('dialog', { name: '新建来源模板' })
    await user.type(within(createDialog).getByLabelText('模板名称'), '药监局公告')
    await user.type(within(createDialog).getByLabelText('任务名称'), 'drug_notice_task')
    await user.type(within(createDialog).getByLabelText('起始地址'), 'https://example.com/notices')
    await user.clear(within(createDialog).getByLabelText('定时表达式'))
    await user.type(within(createDialog).getByLabelText('定时表达式'), '0 */6 * * *')
    await user.click(within(createDialog).getByLabelText('解析规则 JSON'))
    await user.paste('{"list":"notice"}')
    await user.type(within(createDialog).getByLabelText('模板说明'), '抓取药监局公告')
    await user.type(within(createDialog).getByLabelText('标签'), '政策, 药监')
    await user.click(within(createDialog).getByRole('button', { name: '在线测试' }))
    expect(await within(createDialog).findByText(/测试抓取标题/)).toBeInTheDocument()
    expect(within(createDialog).getByText(/采集完整度：82/)).toBeInTheDocument()
    await user.click(within(createDialog).getByRole('button', { name: '保存模板' }))
    expect(await screen.findByText('药监局公告')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '编辑模板 省科技厅通知' }))
    const editDialog = await screen.findByRole('dialog', { name: '编辑来源模板' })
    const descriptionInput = within(editDialog).getByLabelText('模板说明')
    await user.clear(descriptionInput)
    await user.type(descriptionInput, '自动采集最新项目申报')
    await user.click(within(editDialog).getByRole('button', { name: '保存模板' }))
    expect(await screen.findByRole('status')).toHaveTextContent('模板已更新')

    await user.click(screen.getByRole('button', { name: '删除模板 省科技厅通知' }))
    const deleteDialog = await screen.findByRole('dialog', { name: '确认删除模板' })
    await user.click(within(deleteDialog).getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(screen.queryByText('省科技厅通知')).not.toBeInTheDocument())
  })
})

function renderWithAuth(ui: React.ReactNode, fetcher: typeof fetch) {
  return render(
    <AuthProvider clientFactory={() => new ApiClient({ fetcher, getToken: () => 'token' })}>
      {ui}
    </AuthProvider>,
  )
}

function createTemplate(overrides: Record<string, unknown>) {
  return {
    id: 'template',
    label: '模板',
    name: 'template_task',
    start_url: 'https://example.com',
    cron_expr: '0 */6 * * *',
    parser_rules: null,
    enabled: true,
    description: '模板说明',
    tags: [],
    usage_count: 1,
    last_used_at: '2026-08-03T09:00:00Z',
    ...overrides,
  }
}

function createTask(overrides: Record<string, unknown>) {
  return {
    id: 1,
    name: 'task',
    start_url: 'https://example.com',
    parser_rules: null,
    cron_expr: '0 */6 * * *',
    status: 1,
    last_run_status: 'success',
    last_run_at: '2026-08-03T09:30:00Z',
    last_success_at: '2026-08-03T09:30:00Z',
    last_error_message: null,
    created_at: '2026-08-03T08:00:00Z',
    ...overrides,
  }
}

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

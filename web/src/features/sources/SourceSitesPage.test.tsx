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

  it('keeps routine source actions compact and moves retry into advanced maintenance', async () => {
    const templatesState = {
      current: [
        createTemplate({
          id: 'regional_auto',
          label: '地方科技通知',
          name: 'regional_auto_task',
          description: '自动采集地方科技通知',
          tags: ['地方', '政策'],
          parser_rules: '{"list":"notice"}',
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
    renderWithAuth(<SourceSitesPage />, fetcher)

    expect(await screen.findByRole('heading', { name: '模板与运行状态' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '来源结果' })).toHaveAttribute('data-scroll-region', 'table')
    expect(await screen.findByText('地方科技通知')).toBeInTheDocument()
    expect(screen.getByText('省科技厅通知')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '操作' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建模板' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /使用模板/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /编辑模板/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /全部模板/ }))
    await user.click(screen.getByRole('button', { name: '标签 政策' }))
    expect(screen.getByText('地方科技通知')).toBeInTheDocument()
    expect(screen.getByText('省科技厅通知')).toBeInTheDocument()

    await user.click(screen.getByText('省科技厅通知'))
    const drawer = await screen.findByRole('dialog', { name: '省科技厅通知' })
    await user.click(within(drawer).getByText('高级维护'))
    await user.click(within(drawer).getByRole('button', { name: '重试此来源' }))
    expect(await screen.findByRole('status')).toHaveTextContent('已重新排队执行 省科技厅通知')
  })

  it('supports editing and deleting templates from advanced maintenance', async () => {
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

    await user.click(screen.getByText('省科技厅通知'))
    let drawer = await screen.findByRole('dialog', { name: '省科技厅通知' })
    await user.click(within(drawer).getByText('高级维护'))
    await user.click(within(drawer).getByRole('button', { name: '编辑模板' }))
    const editDialog = await screen.findByRole('dialog', { name: '编辑来源模板' })
    const descriptionInput = within(editDialog).getByLabelText('模板说明')
    await user.clear(descriptionInput)
    await user.type(descriptionInput, '自动采集最新项目申报')
    await user.click(within(editDialog).getByRole('button', { name: '保存模板' }))
    expect(await screen.findByRole('status')).toHaveTextContent('模板已更新')

    await user.click(screen.getByText('省科技厅通知'))
    drawer = await screen.findByRole('dialog', { name: '省科技厅通知' })
    await user.click(within(drawer).getByText('高级维护'))
    await user.click(within(drawer).getByRole('button', { name: '删除模板' }))
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

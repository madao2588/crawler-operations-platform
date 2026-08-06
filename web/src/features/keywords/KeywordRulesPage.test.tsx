import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider } from '../../auth/AuthProvider'
import { ApiClient } from '../../api/client'
import { KeywordRulesPage } from './KeywordRulesPage'

describe('KeywordRulesPage', () => {
  it('shows seeded defaults as configurable database rules', async () => {
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/keywords' && (!init || init.method === 'GET')) {
        return jsonResponse({
          code: 0,
          message: 'ok',
          data: {
            items: [
              createRule({ id: 1, word: '项目申报', is_active: true, is_high_priority: true, is_default: true }),
              createRule({ id: 2, word: '生物医药', is_active: true, is_high_priority: false, is_default: true }),
            ],
            total: 2,
            default_total: 2,
            custom_total: 0,
          },
        })
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })

    renderWithAuth(<KeywordRulesPage />, fetcher)

    expect(await screen.findByText('项目申报')).toBeInTheDocument()
    expect(screen.getByText('生物医药')).toBeInTheDocument()
    expect(screen.getAllByText('系统默认')).toHaveLength(2)
    expect(screen.getByText('系统默认 2 条 · 自定义 0 条')).toBeInTheDocument()
    const defaultRow = screen.getByRole('row', { name: /项目申报/ })
    expect(within(defaultRow).getByRole('button', { name: '编辑' })).toBeInTheDocument()
    expect(within(defaultRow).queryByRole('button', { name: '删除 项目申报' })).not.toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(defaultRow)
    const dialog = await screen.findByRole('dialog', { name: '编辑关键词规则' })
    expect(within(dialog).getByLabelText('关键词')).toBeDisabled()
    expect(within(dialog).getByLabelText('高优先级')).toBeEnabled()
    expect(within(dialog).getByLabelText('启用规则')).toBeEnabled()
  })

  it('guides a first-time user to create the first keyword rule', async () => {
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/keywords' && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: { items: [], total: 0 } })
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })
    const user = userEvent.setup()

    renderWithAuth(<KeywordRulesPage />, fetcher)

    expect(await screen.findByText('还没有关键词规则。')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '新建第一条规则' }))
    expect(await screen.findByRole('dialog', { name: '新建关键词规则' })).toBeInTheDocument()
  })

  it('keeps keyword rules read-only for a regular user', async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse({
        code: 0,
        message: 'ok',
        data: {
          items: [createRule({ id: 1, word: '项目申报', is_active: true })],
          total: 1,
          default_total: 0,
          custom_total: 1,
        },
      }),
    )

    renderWithAuth(<KeywordRulesPage canManage={false} />, fetcher)

    expect(await screen.findByText('项目申报')).toBeInTheDocument()
    expect(screen.getByText(/普通用户为只读模式/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建规则' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停用 项目申报' })).not.toBeInTheDocument()
  })

  it('supports filtering, editing, creating, toggling, and deleting keyword rules', async () => {
    const toggleGate = createDeferred<Response>()
    let rules = [
      createRule({ id: 1, word: '一期申报', is_active: true, is_high_priority: true }),
      createRule({ id: 2, word: '竞争情报', is_active: false, is_high_priority: false }),
      createRule({ id: 3, word: '合作项目', is_active: true, is_high_priority: false }),
    ]

    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/v1/keywords' && (!init || init.method === 'GET')) {
        return jsonResponse({ code: 0, message: 'ok', data: { items: rules, total: rules.length } })
      }
      if (url === '/v1/keywords' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        const created = createRule({
          id: 4,
          word: body.word,
          is_active: body.is_active,
          is_high_priority: body.is_high_priority,
        })
        rules = [created, ...rules]
        return jsonResponse({ code: 0, message: 'ok', data: created })
      }
      if (url === '/v1/keywords/3' && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body))
        rules = rules.map((rule) =>
          rule.id === 3 ? { ...rule, ...body, updated_at: '2026-08-03T11:00:00Z' } : rule,
        )
        return jsonResponse({ code: 0, message: 'ok', data: rules.find((rule) => rule.id === 3) })
      }
      if (url === '/v1/keywords/2/toggle' && init?.method === 'POST') {
        return toggleGate.promise
      }
      if (url === '/v1/keywords/1' && init?.method === 'DELETE') {
        rules = rules.filter((rule) => rule.id !== 1)
        return jsonResponse({ code: 0, message: 'ok', data: { success: true } })
      }
      throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
    })

    const user = userEvent.setup()
    renderWithAuth(<KeywordRulesPage />, fetcher)

    expect(await screen.findByRole('heading', { name: '规则维护' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '规则结果' })).toHaveAttribute('data-scroll-region', 'table')
    expect(screen.queryByText('查看全部规则')).not.toBeInTheDocument()
    expect(screen.queryByText('仅显示启用规则')).not.toBeInTheDocument()
    expect(await screen.findByText('一期申报')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /已启用/ }))
    expect(screen.getByText('合作项目')).toBeInTheDocument()
    expect(screen.queryByText('竞争情报')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '筛选 高优先级' }))
    expect(screen.getByText('一期申报')).toBeInTheDocument()
    expect(screen.queryByText('合作项目')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /规则总数/ }))
    await user.click(screen.getByRole('row', { name: /合作项目/ }))
    const editDialog = await screen.findByRole('dialog', { name: '编辑关键词规则' })
    const wordInput = within(editDialog).getByLabelText('关键词')
    await user.clear(wordInput)
    await user.type(wordInput, '合作立项')
    await user.click(within(editDialog).getByRole('button', { name: '保存' }))

    expect(await screen.findByRole('status')).toHaveTextContent('关键词规则已更新')
    expect(await screen.findByText('合作立项')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const createDialog = await screen.findByRole('dialog', { name: '新建关键词规则' })
    await user.type(within(createDialog).getByLabelText('关键词'), '里程碑')
    await user.click(within(createDialog).getByLabelText('高优先级'))
    await user.click(within(createDialog).getByRole('button', { name: '保存' }))

    expect(await screen.findByText('里程碑')).toBeInTheDocument()

    const toggleButton = screen.getByRole('button', { name: '启用 竞争情报' })
    await user.click(toggleButton)
    expect(toggleButton).toBeDisabled()
    toggleGate.resolve(
      jsonResponse({
        code: 0,
        message: 'ok',
        data: createRule({ id: 2, word: '竞争情报', is_active: true, is_high_priority: false }),
      }),
    )
    rules = rules.map((rule) => (rule.id === 2 ? { ...rule, is_active: true } : rule))

    await waitFor(() => expect(screen.getByRole('button', { name: '停用 竞争情报' })).toBeEnabled())

    await user.click(screen.getByRole('button', { name: '删除 一期申报' }))
    const confirmDialog = await screen.findByRole('dialog', { name: '确认删除规则' })
    await user.click(within(confirmDialog).getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(screen.queryByText('一期申报')).not.toBeInTheDocument())
  })
})

function renderWithAuth(ui: React.ReactNode, fetcher: typeof fetch) {
  return render(
    <AuthProvider clientFactory={() => new ApiClient({ fetcher, getToken: () => 'token' })}>
      {ui}
    </AuthProvider>,
  )
}

function createRule(overrides: Record<string, unknown>) {
  return {
    id: 0,
    word: '',
    is_high_priority: false,
    is_active: true,
    is_default: false,
    created_at: '2026-08-03T10:00:00Z',
    updated_at: '2026-08-03T10:00:00Z',
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

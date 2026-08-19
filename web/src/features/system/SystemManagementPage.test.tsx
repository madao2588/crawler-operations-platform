import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SystemManagementPage } from './SystemManagementPage'
import type {
  LogSummary,
  RunAllEnabledResult,
  TaskDetail,
  TaskListItem,
  TaskLogItem,
  TaskRepository,
  TaskRunResult,
  TaskTemplate,
  TemplateRepository,
} from './types'

const task: TaskListItem = {
  id: 7,
  name: '国家药监局采集',
  start_url: 'https://example.com/notices',
  parser_rules: null,
  cron_expr: '0 */2 * * *',
  status: 1,
  last_run_status: 'failed',
  last_run_at: '2026-07-29T08:00:00Z',
  last_success_at: null,
  last_error_message: 'timeout',
  created_at: '2026-07-20T08:00:00Z',
}

const log: TaskLogItem = {
  id: 31,
  task_id: 7,
  level: 'ERROR',
  message: '抓取请求超时',
  error_stack: null,
  run_summary: null,
  created_at: '2026-07-29T08:01:00Z',
}

const template: TaskTemplate = {
  id: 'nmpa',
  label: '国家药监局模板',
  name: '国家药监局采集',
  start_url: 'https://www.nmpa.gov.cn',
  cron_expr: '0 8,14 * * *',
  parser_rules: '{"title":"h1"}',
  enabled: true,
  description: '项目申报通知模板',
  tags: ['申报通知', '国家级'],
  usage_count: 2,
  last_used_at: '2026-07-30T09:00:00Z',
}

describe('SystemManagementPage', () => {
  it('keeps task and template operations read-only for a regular user', async () => {
    render(
      <SystemManagementPage
        canManage={false}
        taskRepository={new FakeTaskRepository()}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    expect(await screen.findByText(/系统会按计划自动采集/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /一键采集/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建任务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /立即运行/ })).not.toBeInTheDocument()
  })

  it('creates a task from a saved template through the dedicated template action', async () => {
    const user = userEvent.setup()
    render(
      <SystemManagementPage
        initialTab="templates"
        taskRepository={new FakeTaskRepository()}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    expect(await screen.findByText('国家药监局模板')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '使用模板' }))
    expect(await screen.findByRole('dialog', { name: '新建任务' })).toBeInTheDocument()
  })

  it('applies initial log intent and normalizes the level filter', async () => {
    const repository = new FakeTaskRepository()
    render(
      <SystemManagementPage
        initialTab="logs"
        initialTaskId={7}
        initialLogLevel="error"
        taskRepository={repository}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    expect(await screen.findByRole('heading', { name: '全局日志' })).toBeInTheDocument()
    expect(repository.lastLogLevel).toBe('ERROR')
    expect(repository.lastLogTaskId).toBe(7)
    expect(screen.getByDisplayValue('7')).toBeInTheDocument()
  })

  it('switches task metric filters and keeps cards clickable', async () => {
    const repository = new FakeTaskRepository()
    const user = userEvent.setup()
    render(
      <SystemManagementPage
        initialTaskFilter="success"
        taskRepository={repository}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    expect(await screen.findByRole('button', { name: /自动运行/ })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '任务结果' })).toHaveAttribute('data-scroll-region', 'table')
    expect(screen.queryByText('任务、模板和日志分区管理，列表行可打开详情，运行操作会实时反馈。')).not.toBeInTheDocument()
    expect(repository.lastEnabled).toBe('all')
    expect(repository.lastRun).toBe('success')

    const enabledCard = screen.getByRole('button', { name: /自动运行/ })
    expect(enabledCard).toBeEnabled()
    await user.click(enabledCard)

    await waitFor(() => {
      expect(repository.lastEnabled).toBe('enabled')
      expect(repository.lastRun).toBe('all')
    })

    await user.click(screen.getByRole('button', { name: /失败任务/ }))

    await waitFor(() => {
      expect(repository.lastEnabled).toBe('all')
      expect(repository.lastRun).toBe('failed')
    })
  })

  it('presents collection as automatic and keeps per-source controls out of the daily task table', async () => {
    const repository = new FakeTaskRepository()
    const user = userEvent.setup()
    render(
      <SystemManagementPage
        taskRepository={repository}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    expect(await screen.findByText('自动运行')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /立即刷新全部/ })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /立即运行/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建任务' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '国家药监局采集' }))
    expect(await screen.findByRole('dialog', { name: '任务详情' })).toBeInTheDocument()
    expect(screen.getAllByText('每 2 小时')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /立即运行/ })).not.toBeInTheDocument()
    expect(screen.getByText('高级维护')).toBeInTheDocument()
  })

  it('filters logs by level and opens the related task from a log row', async () => {
    const repository = new FakeTaskRepository()
    const user = userEvent.setup()
    render(
      <SystemManagementPage
        initialTab="logs"
        taskRepository={repository}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    await user.click(await screen.findByRole('button', { name: /ERROR/ }))
    await waitFor(() => {
      expect(repository.lastLogLevel).toBe('ERROR')
    })

    await user.click(screen.getByRole('button', { name: /抓取请求超时/ }))

    await waitFor(() => {
      expect(repository.fetchTaskIds).toContain(7)
    })
    expect(await screen.findByRole('dialog', { name: '任务详情' })).toBeInTheDocument()
  })

  it('uses one bulk refresh trigger and disables it while the request is pending', async () => {
    const repository = new FakeTaskRepository()
    repository.runAllEnabledDeferred = createDeferred<RunAllEnabledResult>()
    const user = userEvent.setup()
    render(
      <SystemManagementPage
        taskRepository={repository}
        templateRepository={new FakeTemplateRepository()}
      />,
    )

    const heroTrigger = await screen.findByRole('button', { name: /立即刷新全部/ })

    await user.click(heroTrigger)

    expect(repository.runAllEnabledCalls).toBe(1)
    expect(heroTrigger).toBeDisabled()

    repository.runAllEnabledDeferred.resolve({
      queued_task_ids: [7],
      skipped_task_ids: [],
      recovered_task_ids: [],
      quarantined_task_ids: [],
      errors: [],
    })

    expect(await screen.findByText(/已触发 1 个启用任务/)).toBeInTheDocument()
  })
})

class FakeTaskRepository implements TaskRepository {
  lastEnabled = 'all'
  lastRun = 'all'
  lastLogLevel: string | null = null
  lastLogTaskId: number | null = null
  fetchTaskIds: number[] = []
  runTaskCalls = 0
  runAllEnabledCalls = 0
  runTaskDeferred: Deferred<TaskRunResult> | null = null
  runAllEnabledDeferred: Deferred<RunAllEnabledResult> | null = null

  async fetchTasks(params: {
    page: number
    pageSize: number
    search?: string
    enabled?: string
    lastRun?: string
    sortBy?: string
    sortDir?: string
  }) {
    if (params.pageSize === 20) {
      this.lastEnabled = params.enabled ?? 'all'
      this.lastRun = params.lastRun ?? 'all'
    }
    return {
      items: [task],
      total: 1,
      page: params.page,
      page_size: params.pageSize,
    }
  }

  async fetchTask(taskId: number): Promise<TaskDetail> {
    this.fetchTaskIds.push(taskId)
    return { ...task }
  }

  async createTask() {
    return { ...task }
  }

  async updateTask() {
    return { ...task }
  }

  async deleteTask() {}

  runTask() {
    this.runTaskCalls += 1
    return (
      this.runTaskDeferred?.promise ??
      Promise.resolve({
        task_id: 7,
        status: 'queued',
        recovered_stale_run: false,
      })
    )
  }

  runAllEnabledTasks() {
    this.runAllEnabledCalls += 1
    return (
      this.runAllEnabledDeferred?.promise ??
      Promise.resolve({
        queued_task_ids: [7],
        skipped_task_ids: [],
        recovered_task_ids: [],
        quarantined_task_ids: [],
        errors: [],
      })
    )
  }

  async fetchTaskLogs() {
    return {
      items: [log],
      total: 1,
      page: 1,
      page_size: 20,
    }
  }

  async fetchLogs(params: {
    page: number
    pageSize: number
    taskId?: number
    level?: string
    messageContains?: string
  }) {
    this.lastLogTaskId = params.taskId ?? null
    this.lastLogLevel = params.level ?? null
    return {
      items: [log],
      total: 1,
      page: params.page,
      page_size: params.pageSize,
    }
  }

  async fetchLogSummary(): Promise<LogSummary> {
    return {
      total_logs: 3,
      info_logs: 1,
      warning_logs: 1,
      error_logs: 1,
      failed_task_count: 1,
    }
  }
}

class FakeTemplateRepository implements TemplateRepository {
  async fetchTaskTemplates() {
    return [template]
  }

  async createTaskTemplate(input: TaskTemplate) {
    return input
  }

  async updateTaskTemplate(_templateId: string, input: TaskTemplate) {
    return input
  }

  async deleteTaskTemplate() {}

  async trackTaskTemplateUse() {
    return template
  }

}

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve
  })
  return { promise, resolve }
}

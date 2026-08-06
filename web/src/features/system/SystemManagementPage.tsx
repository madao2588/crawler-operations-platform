import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent, MouseEvent } from 'react'
import { MoreHorizontal, Play, Plus, RefreshCw } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useAppLocation } from '../../app/router'
import { useAuth } from '../../auth/AuthProvider'
import { PageToolbar } from '../../components/UiPrimitives'
import { createTaskRepository, createTemplateRepository } from './api'
import { AccountManagementPanel } from './AccountManagementPanel'
import './SystemManagementPage.css'
import type {
  LogSummary,
  PageData,
  RunAllEnabledResult,
  SystemTab,
  TaskDetail,
  TaskListItem,
  TaskLogItem,
  TaskRepository,
  TaskRunResult,
  TaskTemplate,
  TaskTemplateInput,
  TaskTemplate as TaskTemplateModel,
  TemplateRepository,
} from './types'

type TaskFilter = 'all' | 'enabled' | 'disabled' | 'active' | 'success' | 'failed' | 'never'
type LogLevel = 'all' | 'INFO' | 'WARNING' | 'ERROR'

interface SystemManagementPageProps {
  initialTab?: SystemTab
  initialTaskFilter?: string
  initialLogLevel?: string
  initialTaskId?: number
  taskRepository?: TaskRepository
  templateRepository?: TemplateRepository
  canManage?: boolean
}

interface TaskEditorState {
  mode: 'create' | 'edit'
  task?: TaskDetail
  template?: TaskTemplate
}

interface TemplateEditorState {
  mode: 'create' | 'edit'
  template?: TaskTemplate
}

const taskPageSize = 20
const logPageSize = 20

export function SystemManagementPage({
  initialTab = 'tasks',
  initialTaskFilter,
  initialLogLevel,
  initialTaskId,
  taskRepository,
  templateRepository,
  canManage: canManageProp,
}: SystemManagementPageProps) {
  const auth = useOptionalAuth()
  const canManage = canManageProp ?? auth?.session?.user.role !== 'user'
  const canManageAccounts = auth?.session?.user.role === 'admin'
  const location = useAppLocation()
  const tasksApi = useMemo(
    () => taskRepository ?? (auth ? createTaskRepository(auth.client) : null),
    [auth, taskRepository],
  )
  const templatesApi = useMemo(
    () => templateRepository ?? (auth ? createTemplateRepository(auth.client) : null),
    [auth, templateRepository],
  )

  if (!tasksApi || !templatesApi) {
    throw new Error('SystemManagementPage requires repositories or an authenticated AuthProvider.')
  }
  const taskRepo = tasksApi
  const templateRepo = templatesApi

  const [tab, setTab] = useState<SystemTab>(initialTab)
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const [taskPage, setTaskPage] = useState(1)
  const [taskSearch, setTaskSearch] = useState('')
  const [taskSearchDraft, setTaskSearchDraft] = useState('')
  const [taskFilter, setTaskFilter] = useState<TaskFilter>(normalizeTaskFilter(initialTaskFilter))
  const [taskSortBy, setTaskSortBy] = useState<'id' | 'name' | 'last_run_at' | 'created_at'>('id')
  const [taskSortDir, setTaskSortDir] = useState<'asc' | 'desc'>('desc')
  const [tasksPage, setTasksPage] = useState<PageData<TaskListItem> | null>(null)
  const [taskSummaryPage, setTaskSummaryPage] = useState<PageData<TaskListItem> | null>(null)
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)

  const [logPage, setLogPage] = useState(1)
  const [logTaskIdDraft, setLogTaskIdDraft] = useState(initialTab === 'logs' && initialTaskId ? String(initialTaskId) : '')
  const [logTaskId, setLogTaskId] = useState<number | undefined>(initialTab === 'logs' ? initialTaskId : undefined)
  const [logSearchDraft, setLogSearchDraft] = useState('')
  const [logSearch, setLogSearch] = useState('')
  const [logLevel, setLogLevel] = useState<LogLevel>(normalizeLogLevel(initialLogLevel))
  const [logsPage, setLogsPage] = useState<PageData<TaskLogItem> | null>(null)
  const [logSummary, setLogSummary] = useState<LogSummary | null>(null)
  const [logsLoading, setLogsLoading] = useState(initialTab === 'logs')
  const [logsError, setLogsError] = useState<string | null>(null)

  const [templates, setTemplates] = useState<TaskTemplateModel[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(true)
  const [templatesError, setTemplatesError] = useState<string | null>(null)
  const [templateTagFilter, setTemplateTagFilter] = useState('all')

  const [selectedTask, setSelectedTask] = useState<TaskDetail | null>(null)
  const [detailLogs, setDetailLogs] = useState<PageData<TaskLogItem> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [taskEditor, setTaskEditor] = useState<TaskEditorState | null>(null)
  const [templateEditor, setTemplateEditor] = useState<TemplateEditorState | null>(null)

  const [runningTaskIds, setRunningTaskIds] = useState<number[]>([])
  const [bulkRunning, setBulkRunning] = useState(false)
  const [logsRefreshing, setLogsRefreshing] = useState(false)
  const [taskTogglingIds, setTaskTogglingIds] = useState<number[]>([])
  const [deletingTaskIds, setDeletingTaskIds] = useState<number[]>([])
  const [templateBusyIds, setTemplateBusyIds] = useState<string[]>([])

  const openedInitialTaskRef = useRef<number | null>(null)
  const openedTemplateRef = useRef<string | null>(null)

  useEffect(() => {
    setTab(initialTab === 'accounts' && !canManageAccounts ? 'tasks' : initialTab)
  }, [canManageAccounts, initialTab])

  useEffect(() => {
    const nextFilter = normalizeTaskFilter(initialTaskFilter)
    setTaskFilter(nextFilter)
    setTaskPage(1)
  }, [initialTaskFilter])

  useEffect(() => {
    const nextLevel = normalizeLogLevel(initialLogLevel)
    setLogLevel(nextLevel)
    setLogPage(1)
  }, [initialLogLevel])

  useEffect(() => {
    if (initialTab === 'logs') {
      setLogTaskId(initialTaskId)
      setLogTaskIdDraft(initialTaskId ? String(initialTaskId) : '')
    }
  }, [initialTab, initialTaskId])

  useEffect(() => {
    let active = true
    setTasksLoading(true)
    setTasksError(null)
    Promise.all([
      taskRepo.fetchTasks({
        page: taskPage,
        pageSize: taskPageSize,
        search: taskSearch || undefined,
        enabled: taskEnabledFilter(taskFilter),
        lastRun: taskResultFilter(taskFilter),
        sortBy: taskSortBy,
        sortDir: taskSortDir,
      }),
      taskRepo.fetchTasks({
        page: 1,
        pageSize: 100,
        sortBy: 'id',
        sortDir: 'desc',
      }),
    ])
      .then(([pageData, summaryData]) => {
        if (!active) return
        setTasksPage(pageData)
        setTaskSummaryPage(summaryData)
      })
      .catch((error) => {
        if (!active) return
        setTasksError(toMessage(error))
      })
      .finally(() => {
        if (active) setTasksLoading(false)
      })
    return () => {
      active = false
    }
  }, [taskFilter, taskPage, taskSearch, taskSortBy, taskSortDir, taskRepo])

  useEffect(() => {
    let active = true
    setTemplatesLoading(true)
    setTemplatesError(null)
    templateRepo
      .fetchTaskTemplates()
      .then((items) => {
        if (active) setTemplates(items)
      })
      .catch((error) => {
        if (active) setTemplatesError(toMessage(error))
      })
      .finally(() => {
        if (active) setTemplatesLoading(false)
      })
    return () => {
      active = false
    }
  }, [templateRepo])

  useEffect(() => {
    let active = true
    if (tab !== 'logs') return
    setLogsLoading(true)
    setLogsError(null)
    Promise.all([
      taskRepo.fetchLogs({
        page: logPage,
        pageSize: logPageSize,
        taskId: logTaskId,
        level: logLevel === 'all' ? undefined : logLevel,
        messageContains: logSearch || undefined,
      }),
      taskRepo.fetchLogSummary(),
    ])
      .then(([pageData, summaryData]) => {
        if (!active) return
        setLogsPage(pageData)
        setLogSummary(summaryData)
      })
      .catch((error) => {
        if (!active) return
        setLogsError(toMessage(error))
      })
      .finally(() => {
        if (active) setLogsLoading(false)
      })
    return () => {
      active = false
    }
  }, [logLevel, logPage, logSearch, logTaskId, tab, taskRepo])

  useEffect(() => {
    if (tab !== 'tasks' || !initialTaskId || openedInitialTaskRef.current === initialTaskId) return
    if (!tasksPage) return
    openedInitialTaskRef.current = initialTaskId
    void openTaskDetails(initialTaskId)
  }, [initialTaskId, tab, tasksPage])

  useEffect(() => {
    const templateId = new URLSearchParams(location.search).get('template_id')
    if (!canManage || !templateId || tab !== 'tasks' || !templates.length || openedTemplateRef.current === templateId) return
    const matched = templates.find((item) => item.id === templateId)
    if (!matched) return
    openedTemplateRef.current = templateId
    setTaskEditor({ mode: 'create', template: matched })
    if (matched.tags[0]) setTemplateTagFilter(matched.tags[0])
  }, [canManage, location.search, tab, templates])

  const taskSummary = useMemo(() => buildTaskSummary(taskSummaryPage?.items ?? []), [taskSummaryPage?.items])
  const filteredTemplates = useMemo(() => {
    if (templateTagFilter === 'all') return templates
    return templates.filter((item) => item.tags.includes(templateTagFilter))
  }, [templateTagFilter, templates])
  const templateTags = useMemo(() => uniqueTags(templates), [templates])

  async function openTaskDetails(taskId: number) {
    setDetailLoading(true)
    setDetailError(null)
    try {
      const [taskData, taskLogs] = await Promise.all([
        taskRepo.fetchTask(taskId),
        taskRepo.fetchTaskLogs({ taskId, page: 1, pageSize: 10, onlySummary: true }),
      ])
      setSelectedTask(taskData)
      setDetailLogs(taskLogs)
    } catch (error) {
      setDetailError(toMessage(error))
      setFeedback({ tone: 'error', message: `打开任务详情失败：${toMessage(error)}` })
    } finally {
      setDetailLoading(false)
    }
  }

  async function handleTaskRun(taskId: number) {
    if (!canManage || runningTaskIds.includes(taskId)) return
    setRunningTaskIds((current) => [...current, taskId])
    try {
      const result = await taskRepo.runTask(taskId)
      setFeedback({
        tone: 'success',
        message: `任务 ${result.task_id} 已进入队列，系统会继续刷新状态。`,
      })
      await refreshTasks()
      if (tab === 'logs') await refreshLogs()
    } catch (error) {
      setFeedback({ tone: 'error', message: `运行任务失败：${toMessage(error)}` })
    } finally {
      setRunningTaskIds((current) => current.filter((item) => item !== taskId))
    }
  }

  async function handleBulkRun() {
    if (!canManage || bulkRunning) return
    setBulkRunning(true)
    try {
      const result = await taskRepo.runAllEnabledTasks()
      setFeedback({ tone: 'success', message: summarizeBulkRun(result) })
      await refreshTasks()
      if (tab === 'logs') await refreshLogs()
    } catch (error) {
      setFeedback({ tone: 'error', message: `批量采集失败：${toMessage(error)}` })
    } finally {
      setBulkRunning(false)
    }
  }

  async function handleToggleTask(task: TaskListItem) {
    if (!canManage || taskTogglingIds.includes(task.id)) return
    setTaskTogglingIds((current) => [...current, task.id])
    try {
      await taskRepo.updateTask(task.id, { status: task.status === 1 ? 0 : 1 })
      setFeedback({ tone: 'success', message: task.status === 1 ? '任务已停用。' : '任务已启用。' })
      await refreshTasks()
    } catch (error) {
      setFeedback({ tone: 'error', message: `更新任务失败：${toMessage(error)}` })
    } finally {
      setTaskTogglingIds((current) => current.filter((item) => item !== task.id))
    }
  }

  async function handleDeleteTask(task: TaskListItem) {
    if (!canManage || deletingTaskIds.includes(task.id)) return
    if (!window.confirm(`确认删除“${task.name}”吗？`)) return
    setDeletingTaskIds((current) => [...current, task.id])
    try {
      await taskRepo.deleteTask(task.id)
      setFeedback({ tone: 'success', message: '任务已删除。' })
      await refreshTasks()
      if (selectedTask?.id === task.id) setSelectedTask(null)
    } catch (error) {
      setFeedback({ tone: 'error', message: `删除任务失败：${toMessage(error)}` })
    } finally {
      setDeletingTaskIds((current) => current.filter((item) => item !== task.id))
    }
  }

  async function handleSaveAsTemplate(task: TaskListItem) {
    if (!canManage) return
    const input: TaskTemplateInput = {
      label: `${task.name} 模板`,
      name: task.name,
      start_url: task.start_url,
      cron_expr: task.cron_expr,
      parser_rules: task.parser_rules,
      enabled: task.status === 1,
      description: `基于任务“${task.name}”创建的模板`,
      tags: ['任务模板'],
    }
    try {
      await templateRepo.createTaskTemplate(input)
      setFeedback({ tone: 'success', message: `已根据“${task.name}”生成模板。` })
      await refreshTemplates()
    } catch (error) {
      setFeedback({ tone: 'error', message: `保存模板失败：${toMessage(error)}` })
    }
  }

  async function handleUseTemplate(templateItem: TaskTemplate) {
    if (!canManage || templateBusyIds.includes(templateItem.id)) return
    setTemplateBusyIds((current) => [...current, templateItem.id])
    try {
      const tracked = await templateRepo.trackTaskTemplateUse(templateItem.id)
      setTaskEditor({ mode: 'create', template: tracked })
    } catch (error) {
      setFeedback({ tone: 'error', message: `使用模板失败：${toMessage(error)}` })
    } finally {
      setTemplateBusyIds((current) => current.filter((item) => item !== templateItem.id))
    }
  }

  async function handleManualCollect(templateItem: TaskTemplate) {
    if (!canManage || templateBusyIds.includes(templateItem.id)) return
    const url = window.prompt('输入需要登记的文章链接', templateItem.start_url)
    if (!url?.trim()) return
    setTemplateBusyIds((current) => [...current, templateItem.id])
    try {
      const result = await templateRepo.collectManualSource(templateItem.id, url.trim())
      setFeedback({
        tone: 'success',
        message: `文章已登记，公告 ID ${result.notice_id}，状态 ${result.status}。`,
      })
    } catch (error) {
      setFeedback({ tone: 'error', message: `登记文章失败：${toMessage(error)}` })
    } finally {
      setTemplateBusyIds((current) => current.filter((item) => item !== templateItem.id))
    }
  }

  async function handleDeleteTemplate(templateId: string) {
    if (!canManage || templateBusyIds.includes(templateId)) return
    if (!window.confirm('确认删除这个任务模板吗？')) return
    setTemplateBusyIds((current) => [...current, templateId])
    try {
      await templateRepo.deleteTaskTemplate(templateId)
      setFeedback({ tone: 'success', message: '模板已删除。' })
      await refreshTemplates()
    } catch (error) {
      setFeedback({ tone: 'error', message: `删除模板失败：${toMessage(error)}` })
    } finally {
      setTemplateBusyIds((current) => current.filter((item) => item !== templateId))
    }
  }

  async function refreshTasks() {
    const [pageData, summaryData] = await Promise.all([
      taskRepo.fetchTasks({
        page: taskPage,
        pageSize: taskPageSize,
        search: taskSearch || undefined,
        enabled: taskEnabledFilter(taskFilter),
        lastRun: taskResultFilter(taskFilter),
        sortBy: taskSortBy,
        sortDir: taskSortDir,
      }),
      taskRepo.fetchTasks({
        page: 1,
        pageSize: 100,
        sortBy: 'id',
        sortDir: 'desc',
      }),
    ])
    setTasksPage(pageData)
    setTaskSummaryPage(summaryData)
  }

  async function refreshLogs() {
    if (logsRefreshing) return
    setLogsRefreshing(true)
    try {
      const [pageData, summaryData] = await Promise.all([
      taskRepo.fetchLogs({
          page: logPage,
          pageSize: logPageSize,
          taskId: logTaskId,
          level: logLevel === 'all' ? undefined : logLevel,
          messageContains: logSearch || undefined,
        }),
      taskRepo.fetchLogSummary(),
      ])
      setLogsPage(pageData)
      setLogSummary(summaryData)
    } catch (error) {
      setFeedback({ tone: 'error', message: `刷新日志失败：${toMessage(error)}` })
    } finally {
      setLogsRefreshing(false)
    }
  }

  async function refreshTemplates() {
    const items = await templateRepo.fetchTaskTemplates()
    setTemplates(items)
  }

  function submitTaskSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTaskPage(1)
    setTaskSearch(taskSearchDraft.trim())
  }

  function submitLogFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLogPage(1)
    setLogSearch(logSearchDraft.trim())
    setLogTaskId(parseTaskId(logTaskIdDraft))
  }

  return (
    <section className="system-page">
      <PageToolbar
        title="运行与故障处理"
        actions={canManage ? (
          <div className="system-hero-actions">
          <button
            className="primary-action"
            type="button"
            disabled={bulkRunning}
            onClick={handleBulkRun}
          >
            <Play aria-hidden="true" />
            {bulkRunning ? '采集中' : '一键采集'}
          </button>
          </div>
        ) : undefined}
      />

      {feedback ? (
        <p className={`system-feedback system-feedback--${feedback.tone}`} role="status">
          {feedback.message}
        </p>
      ) : null}
      {!canManage ? <p className="read-only-banner">普通用户为只读模式，可查看任务、模板和日志，运行或配置修改请联系管理员。</p> : null}

      <nav className="system-tabs" aria-label="系统管理分区">
        <button
          className={tab === 'tasks' ? 'tab-button is-active' : 'tab-button'}
          type="button"
          onClick={() => setTab('tasks')}
        >
          任务调度
        </button>
        <button
          className={tab === 'templates' ? 'tab-button is-active' : 'tab-button'}
          type="button"
          onClick={() => setTab('templates')}
        >
          任务模板
        </button>
        <button
          className={tab === 'logs' ? 'tab-button is-active' : 'tab-button'}
          type="button"
          onClick={() => setTab('logs')}
        >
          全局日志
        </button>
        {canManageAccounts ? (
          <button
            className={tab === 'accounts' ? 'tab-button is-active' : 'tab-button'}
            type="button"
            onClick={() => setTab('accounts')}
          >
            账号管理
          </button>
        ) : null}
      </nav>

      {tab === 'tasks' ? (
        <section className="panel">
            <div className="panel-header">
              <h2>任务调度</h2>
              {canManage ? <div className="panel-actions">
                <button
                  className="secondary-action system-icon-action"
                  type="button"
                  aria-label="刷新全部启用任务"
                  title="刷新全部启用任务"
                  disabled={bulkRunning}
                  onClick={handleBulkRun}
                >
                  <RefreshCw aria-hidden="true" />
                </button>
                <button className="secondary-action" type="button" onClick={() => setTaskEditor({ mode: 'create' })}>
                  <Plus aria-hidden="true" />
                  新建任务
                </button>
              </div> : null}
            </div>
            <TaskMetricGrid summary={taskSummary} activeFilter={taskFilter} onSelect={setTaskFilter} />

            <form className="filter-row" onSubmit={submitTaskSearch}>
              <label>
                <span>搜索任务</span>
                <input
                  value={taskSearchDraft}
                  onChange={(event) => setTaskSearchDraft(event.target.value)}
                  placeholder="任务名 / URL / Cron"
                />
              </label>
              <details className="advanced-filter">
                <summary>排序</summary>
                <div className="advanced-filter__fields">
                  <label>
                    <span>排序字段</span>
                    <select value={taskSortBy} onChange={(event) => setTaskSortBy(event.target.value as typeof taskSortBy)}>
                      <option value="id">任务 ID</option>
                      <option value="name">名称</option>
                      <option value="last_run_at">最近运行</option>
                      <option value="created_at">创建时间</option>
                    </select>
                  </label>
                  <label>
                    <span>排序方向</span>
                    <select value={taskSortDir} onChange={(event) => setTaskSortDir(event.target.value as typeof taskSortDir)}>
                      <option value="desc">降序</option>
                      <option value="asc">升序</option>
                    </select>
                  </label>
                </div>
              </details>
              <button className="secondary-action" type="submit">
                应用筛选
              </button>
            </form>

            {tasksLoading ? <PanelMessage>任务加载中…</PanelMessage> : null}
            {tasksError ? (
              <PanelError message={tasksError} onRetry={() => void refreshTasks()} />
            ) : null}
            {!tasksLoading && !tasksError && !tasksPage?.items.length ? <PanelMessage>暂无任务。</PanelMessage> : null}
            {!tasksLoading && !tasksError && tasksPage?.items.length ? (
              <>
                <div className="table-shell" role="region" aria-label="任务结果" data-scroll-region="table" tabIndex={0}>
                  <table className="data-table task-table">
                    <thead>
                      <tr>
                        <th>任务</th>
                        <th>Cron</th>
                        <th>状态</th>
                        <th>最近运行</th>
                        <th>最近结果</th>
                        {canManage ? <th>操作</th> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {tasksPage.items.map((item) => {
                        const taskBusy = runningTaskIds.includes(item.id)
                        const toggling = taskTogglingIds.includes(item.id)
                        const deleting = deletingTaskIds.includes(item.id)
                        return (
                          <tr
                            key={item.id}
                            className="table-row-button"
                            tabIndex={0}
                            onClick={() => void openTaskDetails(item.id)}
                            onKeyDown={(event) => handleRowKey(event, () => void openTaskDetails(item.id))}
                          >
                            <td>
                              <button className="row-title-button" type="button" onClick={() => void openTaskDetails(item.id)}>
                                {item.name}
                              </button>
                              <div className="row-meta">{item.start_url}</div>
                            </td>
                            <td>{item.cron_expr}</td>
                            <td>
                              <span className={item.status === 1 ? 'status-badge is-success' : 'status-badge'}>
                                {item.status === 1 ? '已启用' : '已停用'}
                              </span>
                            </td>
                            <td>{formatDateTime(item.last_run_at)}</td>
                            <td>{describeTaskResult(item.last_run_status, item.last_error_message)}</td>
                            {canManage ? <td>
                              <div className="row-actions" onClick={stopPropagation}>
                                <button
                                  className="primary-inline-action"
                                  type="button"
                                  disabled={taskBusy}
                                  onClick={() => void handleTaskRun(item.id)}
                                >
                                  {taskBusy ? '提交中' : '立即运行'}
                                </button>
                                <details className="row-more">
                                  <summary aria-label={`更多任务操作 ${item.name}`}>
                                    <MoreHorizontal aria-hidden="true" />
                                  </summary>
                                  <div className="row-more-menu">
                                    <button className="ghost-action" type="button" disabled={toggling} onClick={() => void handleToggleTask(item)}>
                                      {toggling ? '处理中' : item.status === 1 ? '停用' : '启用'}
                                    </button>
                                    <button className="ghost-action" type="button" onClick={() => setTaskEditor({ mode: 'edit', task: item })}>
                                      编辑
                                    </button>
                                    <button className="ghost-action" type="button" onClick={() => void handleSaveAsTemplate(item)}>
                                      另存模板
                                    </button>
                                    <button className="ghost-action is-danger" type="button" disabled={deleting} onClick={() => void handleDeleteTask(item)}>
                                      {deleting ? '删除中' : '删除'}
                                    </button>
                                  </div>
                                </details>
                              </div>
                            </td> : null}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={tasksPage.page}
                  total={tasksPage.total}
                  pageSize={tasksPage.page_size}
                  onPrevious={tasksPage.page > 1 ? () => setTaskPage((value) => value - 1) : undefined}
                  onNext={tasksPage.page * tasksPage.page_size < tasksPage.total ? () => setTaskPage((value) => value + 1) : undefined}
                />
              </>
            ) : null}
        </section>
      ) : null}

      {tab === 'templates' ? (
        <section className="panel">
            <div className="panel-header">
              <h2>任务模板</h2>
              {canManage ? <div className="panel-actions">
                <button className="secondary-action" type="button" onClick={() => setTemplateEditor({ mode: 'create' })}>
                  <Plus aria-hidden="true" />
                  新建模板
                </button>
              </div> : null}
            </div>
            <div className="tag-row">
              <button
                className={templateTagFilter === 'all' ? 'tag-chip is-active' : 'tag-chip'}
                type="button"
                onClick={() => setTemplateTagFilter('all')}
              >
                全部模板
              </button>
              {templateTags.map((tag) => (
                <button
                  key={tag}
                  className={templateTagFilter === tag ? 'tag-chip is-active' : 'tag-chip'}
                  type="button"
                  onClick={() => setTemplateTagFilter(tag)}
                >
                  {tag}
                </button>
              ))}
            </div>
            {templatesLoading ? <PanelMessage>模板加载中…</PanelMessage> : null}
            {templatesError ? <PanelError message={templatesError} onRetry={() => void refreshTemplates()} /> : null}
            {!templatesLoading && !templatesError && !filteredTemplates.length ? <PanelMessage>暂无模板。</PanelMessage> : null}
            {!templatesLoading && !templatesError && filteredTemplates.length ? (
              <div className="template-grid" role="region" aria-label="模板结果" data-scroll-region="grid" tabIndex={0}>
                {filteredTemplates.map((item) => {
                  const busy = templateBusyIds.includes(item.id)
                  return (
                    <article
                      key={item.id}
                      className="template-card"
                      tabIndex={0}
                      onClick={canManage ? () => setTemplateEditor({ mode: 'edit', template: item }) : undefined}
                      onKeyDown={canManage ? (event) => handleRowKey(event, () => setTemplateEditor({ mode: 'edit', template: item })) : undefined}
                    >
                      <div className="template-card-header">
                        <div>
                          <h3>{item.label}</h3>
                          <p>{item.description}</p>
                        </div>
                        <span className="status-badge">{item.enabled ? '启用模板' : '停用模板'}</span>
                      </div>
                      <p className="row-meta">{item.start_url}</p>
                      <div className="tag-row">
                        {item.tags.map((tag) => (
                          <button
                            key={tag}
                            className="tag-chip"
                            type="button"
                            onClick={(event) => {
                              stopPropagation(event)
                              setTemplateTagFilter(tag)
                            }}
                          >
                            {tag}
                          </button>
                        ))}
                      </div>
                      {canManage ? <div className="row-actions" onClick={stopPropagation}>
                        <button className="primary-inline-action" type="button" disabled={busy} onClick={() => void handleUseTemplate(item)}>
                          {busy ? '处理中' : '使用模板'}
                        </button>
                        <button className="ghost-action" type="button" disabled={busy} onClick={() => void handleManualCollect(item)}>
                          登记文章
                        </button>
                        <button className="ghost-action" type="button" onClick={() => setTemplateEditor({ mode: 'edit', template: item })}>
                          编辑
                        </button>
                        <button className="ghost-action is-danger" type="button" disabled={busy} onClick={() => void handleDeleteTemplate(item.id)}>
                          删除
                        </button>
                      </div> : null}
                    </article>
                  )
                })}
              </div>
            ) : null}
        </section>
      ) : null}

      {tab === 'logs' ? (
        <section className="panel">
            <div className="panel-header">
              <h2>全局日志</h2>
            <div className="panel-actions">
              <button className="secondary-action" type="button" disabled={logsRefreshing} onClick={() => void refreshLogs()}>
                {logsRefreshing ? '刷新中' : '刷新日志'}
              </button>
            </div>
          </div>
          <LogMetricGrid summary={logSummary} activeLevel={logLevel} onSelect={setLogLevel} />
          <form className="filter-row" onSubmit={submitLogFilter}>
            <label>
              <span>任务 ID</span>
              <input value={logTaskIdDraft} onChange={(event) => setLogTaskIdDraft(event.target.value)} inputMode="numeric" />
            </label>
            <label>
              <span>日志内容</span>
              <input value={logSearchDraft} onChange={(event) => setLogSearchDraft(event.target.value)} placeholder="错误关键词 / 运行摘要" />
            </label>
            <label>
              <span>级别</span>
              <select value={logLevel} onChange={(event) => setLogLevel(normalizeLogLevel(event.target.value))}>
                <option value="all">全部级别</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </label>
            <button className="secondary-action" type="submit">
              应用筛选
            </button>
          </form>
          {logsLoading ? <PanelMessage>日志加载中…</PanelMessage> : null}
          {logsError ? <PanelError message={logsError} onRetry={() => void refreshLogs()} /> : null}
          {!logsLoading && !logsError && !logsPage?.items.length ? <PanelMessage>暂无日志。</PanelMessage> : null}
          {!logsLoading && !logsError && logsPage?.items.length ? (
            <>
              <div className="table-shell" role="region" aria-label="日志结果" data-scroll-region="table" tabIndex={0}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>级别</th>
                      <th>内容</th>
                      <th>任务</th>
                      <th>时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logsPage.items.map((item) => (
                      <tr
                        key={item.id}
                        className={item.task_id ? 'table-row-button' : undefined}
                        tabIndex={item.task_id ? 0 : -1}
                        onClick={item.task_id ? () => void openTaskDetails(item.task_id as number) : undefined}
                        onKeyDown={
                          item.task_id ? (event) => handleRowKey(event, () => void openTaskDetails(item.task_id as number)) : undefined
                        }
                      >
                        <td>
                          <span className={`status-badge ${logTone(item.level)}`}>{item.level.toUpperCase()}</span>
                        </td>
                        <td>
                          {item.task_id ? (
                            <button className="row-title-button" type="button" onClick={() => void openTaskDetails(item.task_id as number)}>
                              {item.message}
                            </button>
                          ) : (
                            <span>{item.message}</span>
                          )}
                          {item.error_stack ? <pre className="error-stack">{item.error_stack}</pre> : null}
                        </td>
                        <td>{item.task_id ? `#${item.task_id}` : '系统'}</td>
                        <td>{formatDateTime(item.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={logsPage.page}
                total={logsPage.total}
                pageSize={logsPage.page_size}
                onPrevious={logsPage.page > 1 ? () => setLogPage((value) => value - 1) : undefined}
                onNext={logsPage.page * logsPage.page_size < logsPage.total ? () => setLogPage((value) => value + 1) : undefined}
              />
            </>
          ) : null}
        </section>
      ) : null}

      {tab === 'accounts' && canManageAccounts && auth?.session ? (
        <AccountManagementPanel client={auth.client} currentUserId={auth.session.user.id} />
      ) : null}

      {selectedTask ? (
        <TaskDetailDialog
          task={selectedTask}
          logs={detailLogs}
          loading={detailLoading}
          error={detailError}
          canManage={canManage}
          onClose={() => setSelectedTask(null)}
          onEdit={() => setTaskEditor({ mode: 'edit', task: selectedTask })}
          onRun={() => void handleTaskRun(selectedTask.id)}
        />
      ) : null}

      {canManage && taskEditor ? (
        <TaskEditorDialog
          state={taskEditor}
          onClose={() => setTaskEditor(null)}
          onSubmit={async (input) => {
            try {
              if (taskEditor.mode === 'edit' && taskEditor.task) {
                await taskRepo.updateTask(taskEditor.task.id, input)
                setFeedback({ tone: 'success', message: '任务已更新。' })
              } else {
                await taskRepo.createTask(input)
                setFeedback({ tone: 'success', message: '任务已创建。' })
              }
              setTaskEditor(null)
              await refreshTasks()
              if (taskEditor.template) {
                await refreshTemplates()
              }
            } catch (error) {
              throw new Error(toMessage(error))
            }
          }}
        />
      ) : null}

      {canManage && templateEditor ? (
        <TemplateEditorDialog
          state={templateEditor}
          onClose={() => setTemplateEditor(null)}
          onSubmit={async (input) => {
            try {
              if (templateEditor.mode === 'edit' && templateEditor.template) {
                await templateRepo.updateTaskTemplate(templateEditor.template.id, input)
                setFeedback({ tone: 'success', message: '模板已更新。' })
              } else {
                await templateRepo.createTaskTemplate(input)
                setFeedback({ tone: 'success', message: '模板已创建。' })
              }
              setTemplateEditor(null)
              await refreshTemplates()
            } catch (error) {
              throw new Error(toMessage(error))
            }
          }}
        />
      ) : null}
    </section>
  )
}

function useOptionalAuth() {
  try {
    return useAuth()
  } catch {
    return null
  }
}

function TaskMetricGrid({
  summary,
  activeFilter,
  onSelect,
}: {
  summary: ReturnType<typeof buildTaskSummary>
  activeFilter: TaskFilter
  onSelect: (value: TaskFilter) => void
}) {
  const cards: Array<{ key: TaskFilter; title: string; value: number }> = [
    { key: 'all', title: '全部任务', value: summary.total },
    { key: 'enabled', title: '已启用', value: summary.enabled },
    { key: 'disabled', title: '已停用', value: summary.disabled },
    { key: 'failed', title: '失败任务', value: summary.failed },
    { key: 'active', title: '运行中', value: summary.active },
  ]

  return (
    <div className="metric-grid">
      {cards.map((card) => (
        <button
          key={card.key}
          className={activeFilter === card.key ? 'metric-card is-active' : 'metric-card'}
          style={{ minHeight: 44 }}
          type="button"
          onClick={() => onSelect(card.key)}
        >
          <span>{card.title}</span>
          <strong>{card.value}</strong>
        </button>
      ))}
    </div>
  )
}

function LogMetricGrid({
  summary,
  activeLevel,
  onSelect,
}: {
  summary: LogSummary | null
  activeLevel: LogLevel
  onSelect: (value: LogLevel) => void
}) {
  if (!summary) return null
  const cards: Array<{ key: LogLevel; title: string; value: number }> = [
    { key: 'all', title: '全部级别', value: summary.total_logs },
    { key: 'INFO', title: 'INFO', value: summary.info_logs },
    { key: 'WARNING', title: 'WARNING', value: summary.warning_logs },
    { key: 'ERROR', title: 'ERROR', value: summary.error_logs },
  ]

  return (
    <div className="metric-grid">
      {cards.map((card) => (
        <button
          key={card.key}
          className={activeLevel === card.key ? 'metric-card is-active' : 'metric-card'}
          style={{ minHeight: 44 }}
          type="button"
          onClick={() => onSelect(card.key)}
        >
          <span>{card.title}</span>
          <strong>{card.value}</strong>
        </button>
      ))}
    </div>
  )
}

function TaskDetailDialog({
  task,
  logs,
  loading,
  error,
  canManage,
  onClose,
  onEdit,
  onRun,
}: {
  task: TaskDetail
  logs: PageData<TaskLogItem> | null
  loading: boolean
  error: string | null
  canManage: boolean
  onClose: () => void
  onEdit: () => void
  onRun: () => void
}) {
  return (
    <div className="dialog-backdrop" role="presentation">
      <div className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="task-detail-title" aria-label="任务详情">
        <div className="dialog-header">
          <div>
            <h2 id="task-detail-title">任务详情</h2>
            <p>{task.name}</p>
          </div>
          <div className="row-actions">
            {canManage ? (
              <>
                <button className="ghost-action" type="button" onClick={onEdit}>
                  编辑
                </button>
                <button className="primary-inline-action" type="button" onClick={onRun}>
                  立即运行
                </button>
              </>
            ) : null}
            <button className="ghost-action" type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="detail-grid">
          <DetailCard label="开始地址" value={task.start_url} />
          <DetailCard label="Cron" value={task.cron_expr} />
          <DetailCard label="状态" value={task.status === 1 ? '已启用' : '已停用'} />
          <DetailCard label="最近运行" value={formatDateTime(task.last_run_at)} />
          <DetailCard label="最近成功" value={formatDateTime(task.last_success_at)} />
          <DetailCard label="最近结果" value={describeTaskResult(task.last_run_status, task.last_error_message)} />
        </div>
        <section className="detail-section">
          <h3>解析规则</h3>
          <pre className="detail-pre">{task.parser_rules || '未配置解析规则'}</pre>
        </section>
        <section className="detail-section">
          <h3>最近日志摘要</h3>
          {loading ? <PanelMessage>日志加载中…</PanelMessage> : null}
          {error ? <PanelMessage>{error}</PanelMessage> : null}
          {!loading && !error && !logs?.items.length ? <PanelMessage>暂无日志。</PanelMessage> : null}
          {!loading && !error && logs?.items.length ? (
            <ul className="detail-log-list">
              {logs.items.map((item) => (
                <li key={item.id}>
                  <strong>{item.level.toUpperCase()}</strong>
                  <span>{item.message}</span>
                  <time>{formatDateTime(item.created_at)}</time>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </div>
  )
}

function TaskEditorDialog({
  state,
  onClose,
  onSubmit,
}: {
  state: TaskEditorState
  onClose: () => void
  onSubmit: (input: { name: string; start_url: string; parser_rules: string | null; cron_expr: string; status: number }) => Promise<void>
}) {
  const task = state.task
  const template = state.template
  const [name, setName] = useState(task?.name ?? template?.name ?? '')
  const [startUrl, setStartUrl] = useState(task?.start_url ?? template?.start_url ?? '')
  const [cronExpr, setCronExpr] = useState(task?.cron_expr ?? template?.cron_expr ?? '0 8 * * *')
  const [parserRules, setParserRules] = useState(task?.parser_rules ?? template?.parser_rules ?? '')
  const [enabled, setEnabled] = useState((task?.status ?? (template ? (template.enabled ? 1 : 0) : 1)) === 1)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    try {
      await onSubmit({
        name: name.trim(),
        start_url: startUrl.trim(),
        parser_rules: parserRules.trim() || null,
        cron_expr: cronExpr.trim(),
        status: enabled ? 1 : 0,
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存任务失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <div className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="task-editor-title">
        <div className="dialog-header">
          <div>
            <h2 id="task-editor-title">{state.mode === 'edit' ? '编辑任务' : '新建任务'}</h2>
            <p>{template ? `基于模板“${template.label}”` : '配置采集任务的来源、规则和调度。'}</p>
          </div>
          <button className="ghost-action" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <form className="dialog-form" onSubmit={handleSubmit}>
          <label>
            <span>任务名称</span>
            <input required value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>开始地址</span>
            <input required value={startUrl} onChange={(event) => setStartUrl(event.target.value)} />
          </label>
          <label>
            <span>Cron 表达式</span>
            <input required value={cronExpr} onChange={(event) => setCronExpr(event.target.value)} />
          </label>
          <label>
            <span>解析规则</span>
            <textarea rows={6} value={parserRules} onChange={(event) => setParserRules(event.target.value)} />
          </label>
          <label className="switch-row">
            <input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
            <span>保存后立即启用</span>
          </label>
          {error ? <p className="system-feedback system-feedback--error">{error}</p> : null}
          <div className="dialog-actions">
            <button className="ghost-action" type="button" onClick={onClose} disabled={saving}>
              取消
            </button>
            <button className="primary-action" type="submit" disabled={saving}>
              {saving ? '保存中' : '保存任务'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TemplateEditorDialog({
  state,
  onClose,
  onSubmit,
}: {
  state: TemplateEditorState
  onClose: () => void
  onSubmit: (input: TaskTemplateInput) => Promise<void>
}) {
  const template = state.template
  const [label, setLabel] = useState(template?.label ?? '')
  const [name, setName] = useState(template?.name ?? '')
  const [startUrl, setStartUrl] = useState(template?.start_url ?? '')
  const [cronExpr, setCronExpr] = useState(template?.cron_expr ?? '0 8 * * *')
  const [parserRules, setParserRules] = useState(template?.parser_rules ?? '')
  const [description, setDescription] = useState(template?.description ?? '')
  const [tags, setTags] = useState(template ? template.tags.join(',') : '')
  const [enabled, setEnabled] = useState(template?.enabled ?? true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    try {
      await onSubmit({
        id: template?.id,
        label: label.trim(),
        name: name.trim(),
        start_url: startUrl.trim(),
        cron_expr: cronExpr.trim(),
        parser_rules: parserRules.trim() || null,
        enabled,
        description: description.trim(),
        tags: tags.split(',').map((item) => item.trim()).filter(Boolean),
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存模板失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <div className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="template-editor-title">
        <div className="dialog-header">
          <div>
            <h2 id="template-editor-title">{state.mode === 'edit' ? '编辑模板' : '新建模板'}</h2>
            <p>模板负责沉淀可复用的任务配置和手工登记入口。</p>
          </div>
          <button className="ghost-action" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <form className="dialog-form" onSubmit={handleSubmit}>
          <label>
            <span>模板名称</span>
            <input required value={label} onChange={(event) => setLabel(event.target.value)} />
          </label>
          <label>
            <span>任务名称</span>
            <input required value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>开始地址</span>
            <input required value={startUrl} onChange={(event) => setStartUrl(event.target.value)} />
          </label>
          <label>
            <span>Cron 表达式</span>
            <input required value={cronExpr} onChange={(event) => setCronExpr(event.target.value)} />
          </label>
          <label>
            <span>模板说明</span>
            <textarea required rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label>
            <span>标签</span>
            <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="逗号分隔多个标签" />
          </label>
          <label>
            <span>解析规则</span>
            <textarea rows={6} value={parserRules} onChange={(event) => setParserRules(event.target.value)} />
          </label>
          <label className="switch-row">
            <input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
            <span>启用模板</span>
          </label>
          {error ? <p className="system-feedback system-feedback--error">{error}</p> : null}
          <div className="dialog-actions">
            <button className="ghost-action" type="button" onClick={onClose} disabled={saving}>
              取消
            </button>
            <button className="primary-action" type="submit" disabled={saving}>
              {saving ? '保存中' : '保存模板'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function DetailCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="detail-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}

function Pagination({
  page,
  total,
  pageSize,
  onPrevious,
  onNext,
}: {
  page: number
  total: number
  pageSize: number
  onPrevious?: () => void
  onNext?: () => void
}) {
  return (
    <div className="pagination-bar">
      <span>
        第 {page} 页，共 {total} 条，每页 {pageSize} 条
      </span>
      <div className="row-actions">
        <button className="ghost-action" type="button" onClick={onPrevious} disabled={!onPrevious}>
          上一页
        </button>
        <button className="ghost-action" type="button" onClick={onNext} disabled={!onNext}>
          下一页
        </button>
      </div>
    </div>
  )
}

function PanelMessage({ children }: { children: string }) {
  return <p className="panel-message">{children}</p>
}

function PanelError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="panel-error" role="alert">
      <p>{message}</p>
      <button className="ghost-action" type="button" onClick={onRetry}>
        重试
      </button>
    </div>
  )
}

function buildTaskSummary(items: TaskListItem[]) {
  return items.reduce(
    (summary, item) => {
      summary.total += 1
      if (item.status === 1) summary.enabled += 1
      else summary.disabled += 1
      const normalized = (item.last_run_status ?? '').toLowerCase()
      if (normalized === 'failed') summary.failed += 1
      if (normalized === 'success') summary.success += 1
      if (normalized === 'queued' || normalized === 'running') summary.active += 1
      if (!item.last_run_status) summary.never += 1
      return summary
    },
    { total: 0, enabled: 0, disabled: 0, failed: 0, success: 0, active: 0, never: 0 },
  )
}

function normalizeTaskFilter(value?: string): TaskFilter {
  const normalized = value?.trim().toLowerCase() ?? 'all'
  return ['all', 'enabled', 'disabled', 'active', 'success', 'failed', 'never'].includes(normalized)
    ? (normalized as TaskFilter)
    : 'all'
}

function normalizeLogLevel(value?: string): LogLevel {
  const normalized = value?.trim().toUpperCase() ?? 'ALL'
  return normalized === 'INFO' || normalized === 'WARNING' || normalized === 'ERROR' ? normalized : 'all'
}

function taskEnabledFilter(filter: TaskFilter) {
  if (filter === 'enabled' || filter === 'disabled') return filter
  return 'all'
}

function taskResultFilter(filter: TaskFilter) {
  if (filter === 'success' || filter === 'failed' || filter === 'active' || filter === 'never') return filter
  return 'all'
}

function summarizeBulkRun(result: RunAllEnabledResult) {
  if (result.queued_task_ids.length) {
    return `已触发 ${result.queued_task_ids.length} 个启用任务，${result.skipped_task_ids.length} 个任务被跳过。`
  }
  if (result.skipped_task_ids.length) {
    return `当前没有新的任务入队，${result.skipped_task_ids.length} 个任务仍在运行中。`
  }
  return '当前没有可触发的启用任务。'
}

function parseTaskId(value: string) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
}

function describeTaskResult(status: string | null, errorMessage: string | null) {
  const normalized = (status ?? '').toLowerCase()
  if (!normalized) return '从未运行'
  if (normalized === 'failed' && errorMessage) return `失败 · ${errorMessage}`
  if (normalized === 'queued') return '排队中'
  if (normalized === 'running') return '运行中'
  if (normalized === 'success') return '成功'
  if (normalized === 'partial') return '部分成功'
  return status ?? '未知'
}

function formatDateTime(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function uniqueTags(items: TaskTemplate[]) {
  return [...new Set(items.flatMap((item) => item.tags))].sort((left, right) => left.localeCompare(right, 'zh-CN'))
}

function toMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}

function handleRowKey(event: KeyboardEvent<HTMLElement>, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function stopPropagation(event: MouseEvent<HTMLElement>) {
  event.stopPropagation()
}

function logTone(level: string) {
  const normalized = level.toUpperCase()
  if (normalized === 'ERROR') return 'is-danger'
  if (normalized === 'WARNING') return 'is-warning'
  if (normalized === 'INFO') return 'is-info'
  return ''
}

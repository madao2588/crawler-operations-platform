export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface TaskListItem {
  id: number
  name: string
  start_url: string
  parser_rules: string | null
  cron_expr: string
  status: number
  last_run_status: string | null
  last_run_at: string | null
  last_success_at: string | null
  last_error_message: string | null
  created_at: string
}

export type TaskDetail = TaskListItem

export interface TaskRunResult {
  task_id: number
  status: string
  recovered_stale_run: boolean
}

export interface RunAllEnabledResult {
  queued_task_ids: number[]
  skipped_task_ids: number[]
  recovered_task_ids: number[]
  quarantined_task_ids: number[]
  errors: string[]
}

export interface TaskLogItem {
  id: number
  task_id: number | null
  level: string
  message: string
  error_stack: string | null
  run_summary: {
    run_id?: string | null
    mode?: string
    metrics?: Record<string, string | number | boolean>
  } | null
  created_at: string
}

export interface LogSummary {
  total_logs: number
  info_logs: number
  warning_logs: number
  error_logs: number
  failed_task_count: number
}

export interface TaskTemplate {
  id: string
  label: string
  name: string
  start_url: string
  cron_expr: string
  parser_rules: string | null
  enabled: boolean
  description: string
  tags: string[]
  usage_count: number
  last_used_at: string | null
}

export interface TaskUpsertInput {
  name: string
  start_url: string
  parser_rules?: string | null
  cron_expr: string
  status: number
}

export interface TaskUpdateInput {
  name?: string
  start_url?: string
  parser_rules?: string | null
  cron_expr?: string
  status?: number
}

export interface TaskTemplateInput {
  id?: string
  label: string
  name: string
  start_url: string
  cron_expr: string
  parser_rules?: string | null
  enabled: boolean
  description: string
  tags: string[]
}

export interface TaskRepository {
  fetchTasks(params: {
    page: number
    pageSize: number
    search?: string
    enabled?: string
    lastRun?: string
    sortBy?: string
    sortDir?: string
  }): Promise<PageData<TaskListItem>>
  fetchTask(taskId: number): Promise<TaskDetail>
  createTask(input: TaskUpsertInput): Promise<TaskDetail>
  updateTask(taskId: number, input: TaskUpdateInput): Promise<TaskDetail>
  deleteTask(taskId: number): Promise<void>
  runTask(taskId: number): Promise<TaskRunResult>
  runAllEnabledTasks(): Promise<RunAllEnabledResult>
  fetchTaskLogs(params: {
    taskId: number
    page: number
    pageSize: number
    onlySummary?: boolean
  }): Promise<PageData<TaskLogItem>>
  fetchLogs(params: {
    page: number
    pageSize: number
    taskId?: number
    level?: string
    messageContains?: string
  }): Promise<PageData<TaskLogItem>>
  fetchLogSummary(): Promise<LogSummary>
}

export interface TemplateRepository {
  fetchTaskTemplates(): Promise<TaskTemplate[]>
  createTaskTemplate(input: TaskTemplateInput): Promise<TaskTemplate>
  updateTaskTemplate(templateId: string, input: TaskTemplateInput): Promise<TaskTemplate>
  deleteTaskTemplate(templateId: string): Promise<void>
  trackTaskTemplateUse(templateId: string): Promise<TaskTemplate>
}

export type SystemTab = 'tasks' | 'templates' | 'logs' | 'accounts'

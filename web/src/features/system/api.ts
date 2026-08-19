import { ApiClient } from '../../api/client'
import type {
  LogSummary,
  PageData,
  RunAllEnabledResult,
  TaskDetail,
  TaskListItem,
  TaskLogItem,
  TaskRepository,
  TaskRunResult,
  TaskTemplate,
  TaskTemplateInput,
  TaskUpsertInput,
  TaskUpdateInput,
  TemplateRepository,
} from './types'

export function createTaskRepository(client: ApiClient): TaskRepository {
  return {
    fetchTasks: async ({ page, pageSize, search, enabled = 'all', lastRun = 'all', sortBy = 'id', sortDir = 'desc' }) =>
      client.get<PageData<TaskListItem>>('/v1/tasks', {
        query: {
          page,
          page_size: pageSize,
          search,
          enabled,
          last_run: lastRun,
          sort_by: sortBy,
          sort_dir: sortDir,
        },
      }),
    fetchTask: async (taskId) => client.get<TaskDetail>(`/v1/tasks/${taskId}`),
    createTask: async (input) => client.post<TaskDetail>('/v1/tasks', normalizeTaskInput(input)),
    updateTask: async (taskId, input) => client.put<TaskDetail>(`/v1/tasks/${taskId}`, normalizeTaskInput(input)),
    deleteTask: async (taskId) => {
      await client.delete<Record<string, never>>(`/v1/tasks/${taskId}`)
    },
    runTask: async (taskId) => client.post<TaskRunResult>(`/v1/tasks/${taskId}/run`),
    runAllEnabledTasks: async () => client.post<RunAllEnabledResult>('/v1/tasks/run-enabled'),
    fetchTaskLogs: async ({ taskId, page, pageSize, onlySummary = false }) =>
      client.get<PageData<TaskLogItem>>('/v1/logs', {
        query: {
          task_id: taskId,
          page,
          page_size: pageSize,
          only_summary: onlySummary,
        },
      }),
    fetchLogs: async ({ page, pageSize, taskId, level, messageContains }) =>
      client.get<PageData<TaskLogItem>>('/v1/logs', {
        query: {
          page,
          page_size: pageSize,
          task_id: taskId,
          level,
          message_contains: messageContains,
        },
      }),
    fetchLogSummary: async () => client.get<LogSummary>('/v1/logs/summary'),
  }
}

export function createTemplateRepository(client: ApiClient): TemplateRepository {
  return {
    fetchTaskTemplates: async () => client.get<TaskTemplate[]>('/v1/templates/tasks'),
    createTaskTemplate: async (input) => client.post<TaskTemplate>('/v1/templates/tasks', normalizeTemplateInput(input)),
    updateTaskTemplate: async (templateId, input) =>
      client.put<TaskTemplate>(`/v1/templates/tasks/${templateId}`, normalizeTemplateInput(input)),
    deleteTaskTemplate: async (templateId) => {
      await client.delete<Record<string, never>>(`/v1/templates/tasks/${templateId}`)
    },
    trackTaskTemplateUse: async (templateId) =>
      client.post<TaskTemplate>(`/v1/templates/tasks/${templateId}/use`),
  }
}

function normalizeTaskInput(input: TaskUpsertInput | TaskUpdateInput) {
  return {
    ...(input.name !== undefined ? { name: input.name } : {}),
    ...(input.start_url !== undefined ? { start_url: input.start_url } : {}),
    ...(input.parser_rules !== undefined ? { parser_rules: input.parser_rules } : {}),
    ...(input.cron_expr !== undefined ? { cron_expr: input.cron_expr } : {}),
    ...(input.status !== undefined ? { status: input.status } : {}),
  }
}

function normalizeTemplateInput(input: TaskTemplateInput) {
  return {
    ...(input.id ? { id: input.id } : {}),
    label: input.label,
    name: input.name,
    start_url: input.start_url,
    cron_expr: input.cron_expr,
    parser_rules: input.parser_rules ?? null,
    enabled: input.enabled,
    description: input.description,
    tags: input.tags,
  }
}

import { useEffect, useMemo, useState } from 'react'
import type { FormEvent, MouseEvent, ReactNode } from 'react'
import { ChevronDown, ChevronUp, Plus, RefreshCw, Search } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useAuth } from '../../auth/AuthProvider'
import { DataTableShell, DetailDrawer, PageToolbar } from '../../components/UiPrimitives'
import './SourceSitesPage.css'

type TemplateFilter = 'all' | 'manual' | 'automatic' | 'needsAuth'

interface TemplateDto {
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

interface TemplateModel {
  id: string
  label: string
  name: string
  startUrl: string
  cronExpr: string
  parserRules: string | null
  enabled: boolean
  description: string
  tags: string[]
  usageCount: number
  lastUsedAt: string | null
}

interface TaskListResponse {
  items: TaskDto[]
  total: number
  page: number
  page_size: number
}

interface TaskDto {
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

interface TaskModel {
  id: number
  name: string
  lastRunStatus: string | null
  lastRunAt: string | null
  lastSuccessAt: string | null
  lastErrorMessage: string | null
}

interface LogListResponse {
  items: LogDto[]
}

interface LogDto {
  id: number
  task_id: number | null
  level: string
  message: string
  error_stack: string | null
  run_summary: Record<string, unknown> | null
  created_at: string
}

interface LogModel {
  id: number
  taskId: number | null
  message: string
  errorStack: string | null
  runSummary: Record<string, unknown> | null
}

interface TestTemplateResponse {
  title: string | null
  content_text: string | null
  content_html: string | null
  quality_score: number | null
  error: string | null
  trace: {
    fetch: string | null
    content_source: string | null
    notes: string[]
  } | null
}

interface ManualCollectionResponse {
  source_id: string
  source_url: string
  status: string
  notice_id: number
}

interface TaskRunResponse {
  task_id: number
  status: string
}

interface TemplateHealth {
  task: TaskModel | null
  latestLog: LogModel | null
}

interface TemplateEditorValue {
  label: string
  name: string
  startUrl: string
  cronExpr: string
  parserRules: string
  description: string
  tags: string
  enabled: boolean
}

interface FeedbackState {
  tone: 'success' | 'error'
  message: string
}

interface SourceSitesPageProps {
  onUseTemplate?: (templateId: string) => void
  canManage?: boolean
}

const manualTemplateIds = new Set(['wechat_k_innovation', 'wechat_hengqin_biomed', 'wechat_competitor_intelligence'])
const authorizationTemplateIds = new Set(['pharnexcloud_drug_database'])

export function SourceSitesPage({ onUseTemplate, canManage: canManageProp }: SourceSitesPageProps) {
  const { client, session } = useAuth()
  const canManage = canManageProp ?? session?.user.role !== 'user'
  const [templates, setTemplates] = useState<TemplateModel[]>([])
  const [healthByTemplateId, setHealthByTemplateId] = useState<Record<string, TemplateHealth>>({})
  const [loading, setLoading] = useState(true)
  const [healthLoading, setHealthLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<FeedbackState | null>(null)
  const [templateFilter, setTemplateFilter] = useState<TemplateFilter>('all')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [tagsExpanded, setTagsExpanded] = useState(false)
  const [search, setSearch] = useState('')
  const [detailTemplate, setDetailTemplate] = useState<TemplateModel | null>(null)
  const [editorTemplate, setEditorTemplate] = useState<TemplateModel | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleteTemplate, setDeleteTemplate] = useState<TemplateModel | null>(null)
  const [collectTemplate, setCollectTemplate] = useState<TemplateModel | null>(null)
  const [pendingIds, setPendingIds] = useState<string[]>([])
  const [runningTaskIds, setRunningTaskIds] = useState<number[]>([])

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const tags = useMemo(
    () => Array.from(new Set(templates.flatMap((template) => template.tags))).sort((left, right) => left.localeCompare(right, 'zh-CN')),
    [templates],
  )
  const visibleTags = tagsExpanded ? tags : tags.slice(0, 5)

  const stats = useMemo(() => {
    const kinds = templates.map((template) => resolveCollectionKind(template))
    return {
      total: templates.length,
      manual: kinds.filter((kind) => kind === 'manual').length,
      automatic: kinds.filter((kind) => kind === 'automatic').length,
      needsAuth: kinds.filter((kind) => kind === 'needsAuth').length,
    }
  }, [templates])

  const visibleTemplates = useMemo(() => {
    return templates
      .filter((template) => {
        if (templateFilter !== 'all' && resolveCollectionKind(template) !== templateFilter) return false
        if (selectedTag && !template.tags.includes(selectedTag)) return false
        const query = search.trim().toLowerCase()
        if (!query) return true
        return [
          template.label,
          template.name,
          template.description,
          template.startUrl,
          template.id,
          ...template.tags,
        ].some((value) => value.toLowerCase().includes(query))
      })
      .sort((left, right) => right.usageCount - left.usageCount || left.label.localeCompare(right.label, 'zh-CN'))
  }, [search, selectedTag, templateFilter, templates])

  async function refreshAll() {
    setLoading(true)
    setError(null)
    try {
      const nextTemplates = await loadTemplates()
      setTemplates(nextTemplates)
      await refreshHealth(nextTemplates)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function loadTemplates() {
    const list = await client.get<TemplateDto[]>('/v1/templates/tasks')
    return list.map(mapTemplate)
  }

  async function refreshHealth(sourceTemplates: TemplateModel[]) {
    setHealthLoading(true)
    try {
      const health = await loadTemplateHealth(client, sourceTemplates)
      setHealthByTemplateId(health)
    } catch (requestError) {
      setFeedback({ tone: 'error', message: `任务健康加载失败：${getErrorMessage(requestError)}` })
    } finally {
      setHealthLoading(false)
    }
  }

  async function handleUseTemplate(template: TemplateModel) {
    if (!canManage || pendingIds.includes(template.id)) return
    markPending(template.id, true)
    try {
      await client.post<TemplateDto>(`/v1/templates/tasks/${template.id}/use`)
      const nextTemplates = await loadTemplates()
      setTemplates(nextTemplates)
      setFeedback({ tone: 'success', message: `模板 ${template.label} 已登记使用` })
      onUseTemplate?.(template.id)
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
    } finally {
      markPending(template.id, false)
    }
  }

  async function handleRetryTask(template: TemplateModel) {
    if (!canManage) return
    const task = healthByTemplateId[template.id]?.task
    if (!task || runningTaskIds.includes(task.id)) return
    setRunningTaskIds((current) => [...current, task.id])
    try {
      await client.post<TaskRunResponse>(`/v1/tasks/${task.id}/run`)
      setFeedback({ tone: 'success', message: `已重新排队执行 ${template.label}` })
      await refreshHealth(templates)
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
    } finally {
      setRunningTaskIds((current) => current.filter((id) => id !== task.id))
    }
  }

  async function handleDeleteTemplate() {
    if (!canManage || !deleteTemplate || pendingIds.includes(deleteTemplate.id)) return
    const currentTemplate = deleteTemplate
    markPending(currentTemplate.id, true)
    try {
      await client.delete<Record<string, never>>(`/v1/templates/tasks/${currentTemplate.id}`)
      const nextTemplates = await loadTemplates()
      setTemplates(nextTemplates)
      setDeleteTemplate(null)
      setDetailTemplate((current) => (current?.id === currentTemplate.id ? null : current))
      setFeedback({ tone: 'success', message: `模板 ${currentTemplate.label} 已删除` })
      await refreshHealth(nextTemplates)
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
    } finally {
      markPending(currentTemplate.id, false)
    }
  }

  async function handleSaveTemplate(value: TemplateEditorValue, template: TemplateModel | null) {
    if (!canManage || saving) return
    setSaving(true)
    try {
      const payload = {
        id: template?.id,
        label: value.label.trim(),
        name: value.name.trim(),
        start_url: value.startUrl.trim(),
        cron_expr: value.cronExpr.trim(),
        parser_rules: value.parserRules.trim() || null,
        enabled: value.enabled,
        description: value.description.trim(),
        tags: value.tags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
      }

      if (template) {
        await client.put<TemplateDto>(`/v1/templates/tasks/${template.id}`, payload)
        setFeedback({ tone: 'success', message: '模板已更新' })
      } else {
        await client.post<TemplateDto>('/v1/templates/tasks', payload)
        setFeedback({ tone: 'success', message: '模板已创建' })
      }
      const nextTemplates = await loadTemplates()
      setTemplates(nextTemplates)
      setCreating(false)
      setEditorTemplate(null)
      await refreshHealth(nextTemplates)
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
      throw requestError
    } finally {
      setSaving(false)
    }
  }

  function markPending(templateId: string, pending: boolean) {
    setPendingIds((current) => {
      if (pending) return current.includes(templateId) ? current : [...current, templateId]
      return current.filter((id) => id !== templateId)
    })
  }

  return (
    <section className="source-page">
      <PageToolbar
        title="模板与运行状态"
        actions={
          <div className="source-page__heroActions">
          <button className="source-page__secondaryButton" type="button" onClick={() => void refreshAll()}>
            <RefreshCw aria-hidden="true" />
            {healthLoading ? '刷新中...' : '刷新'}
          </button>
          {canManage ? (
            <button className="source-page__primaryButton" type="button" onClick={() => setCreating(true)}>
              <Plus aria-hidden="true" />
              新建模板
            </button>
          ) : null}
          </div>
        }
      />

      {feedback ? (
        <div className={`source-page__feedback source-page__feedback--${feedback.tone}`} role={feedback.tone === 'error' ? 'alert' : 'status'}>
          {feedback.message}
        </div>
      ) : null}
      {!canManage ? <p className="read-only-banner">普通用户为只读模式，可查看来源和运行状态，配置修改请联系管理员。</p> : null}

      <div className="source-page__stats">
        <StatCard title="全部模板" value={stats.total} active={templateFilter === 'all'} onClick={() => setTemplateFilter('all')} />
        <StatCard title="人工登记" value={stats.manual} active={templateFilter === 'manual'} onClick={() => setTemplateFilter('manual')} />
        <StatCard title="自动采集" value={stats.automatic} active={templateFilter === 'automatic'} onClick={() => setTemplateFilter('automatic')} />
        <StatCard title="需授权" value={stats.needsAuth} active={templateFilter === 'needsAuth'} onClick={() => setTemplateFilter('needsAuth')} />
      </div>

      <div className="source-page__toolbar">
        <label className="source-page__search">
          <span className="source-page__fieldLabel">搜索模板</span>
          <span className="source-page__searchControl">
            <Search aria-hidden="true" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="按模板名、任务名、站点或标签筛选" />
          </span>
        </label>
        <div className="source-page__tagBar">
          {visibleTags.map((tag) => (
            <button
              key={tag}
              className={`source-page__tag ${selectedTag === tag ? 'source-page__tag--active' : ''}`}
              type="button"
              aria-label={`标签 ${tag}`}
              onClick={() => setSelectedTag((current) => (current === tag ? null : tag))}
            >
              {tag}
            </button>
          ))}
          {tags.length > 5 ? (
            <button className="source-page__tag source-page__tagToggle" type="button" onClick={() => setTagsExpanded((value) => !value)}>
              {tagsExpanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
              {tagsExpanded ? '收起标签' : `更多 ${tags.length - 5} 个`}
            </button>
          ) : null}
        </div>
      </div>

      <div className="source-page__panel">
        {loading ? <div className="source-page__state">正在加载来源模板...</div> : null}
        {!loading && error ? (
          <div className="source-page__state source-page__state--error" role="alert">
            <p>{error}</p>
            <button className="source-page__secondaryButton" type="button" onClick={() => void refreshAll()}>
              重试加载
            </button>
          </div>
        ) : null}
        {!loading && !error && visibleTemplates.length === 0 ? (
          <div className="source-page__state">
            <p>当前没有匹配的模板。</p>
            <button
              className="source-page__secondaryButton"
              type="button"
              onClick={() => {
                setTemplateFilter('all')
                setSelectedTag(null)
                setSearch('')
              }}
            >
              清空筛选
            </button>
          </div>
        ) : null}
        {!loading && !error && visibleTemplates.length > 0 ? (
          <DataTableShell className="source-page__tableWrap" ariaLabel="来源结果">
            <table className="source-page__table">
              <thead>
                <tr>
                  <th scope="col">来源模板</th>
                  <th scope="col">采集方式</th>
                  <th scope="col">运行状态</th>
                  <th scope="col">最近使用</th>
                  {canManage ? <th scope="col">操作</th> : null}
                </tr>
              </thead>
              <tbody>
                {visibleTemplates.map((template) => {
                  const health = healthByTemplateId[template.id] ?? { task: null, latestLog: null }
                  const runtime = resolveRuntimeStatus(template, health)
                  const pending = pendingIds.includes(template.id)
                  const retrying = health.task ? runningTaskIds.includes(health.task.id) : false
                  return (
                    <tr
                      key={template.id}
                      className="source-page__row"
                      tabIndex={0}
                      onClick={() => setDetailTemplate(template)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setDetailTemplate(template)
                        }
                      }}
                    >
                      <td>
                        <div className="source-page__templateCell">
                          <strong>{template.label}</strong>
                          <span>{template.description}</span>
                          <div className="source-page__cardTags">
                            {template.tags.slice(0, 3).map((tag) => (
                              <button
                                key={tag}
                                className="source-page__tag"
                                type="button"
                                aria-label={`卡片标签 ${tag}`}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setSelectedTag(tag)
                                }}
                              >
                                {tag}
                              </button>
                            ))}
                          </div>
                        </div>
                      </td>
                      <td>
                        <strong className="source-page__kind">{collectionKindLabel(resolveCollectionKind(template))}</strong>
                        <span className="source-page__cellMeta">{template.name}</span>
                      </td>
                      <td>
                        <span className={`source-page__statusBadge source-page__statusBadge--${runtime.tone}`}>{runtime.label}</span>
                        <span className="source-page__cellMeta">{runtime.note}</span>
                      </td>
                      <td>
                        <strong>{formatDateTime(template.lastUsedAt)}</strong>
                        <span className="source-page__cellMeta">累计 {template.usageCount} 次</span>
                      </td>
                      {canManage ? <td>
                        <div className="source-page__cardActions">
                          <button className="source-page__primaryButton" type="button" aria-label={`使用模板 ${template.label}`} onClick={(event) => { event.stopPropagation(); void handleUseTemplate(template) }} disabled={pending}>
                            {pending ? '处理中...' : '使用'}
                          </button>
                          <button className="source-page__secondaryButton" type="button" aria-label={`登记文章 ${template.label}`} onClick={(event) => { event.stopPropagation(); setCollectTemplate(template) }}>
                            登记
                          </button>
                          <button className="source-page__secondaryButton" type="button" aria-label={`编辑模板 ${template.label}`} onClick={(event) => { event.stopPropagation(); setEditorTemplate(template) }}>
                            编辑
                          </button>
                          <button className="source-page__secondaryButton source-page__secondaryButton--danger" type="button" aria-label={`删除模板 ${template.label}`} onClick={(event) => { event.stopPropagation(); setDeleteTemplate(template) }} disabled={pending}>
                            删除
                          </button>
                          {runtime.canRetry && health.task ? (
                            <button className="source-page__secondaryButton" type="button" aria-label={`重试任务 ${template.label}`} onClick={(event) => { event.stopPropagation(); void handleRetryTask(template) }} disabled={retrying}>
                              {retrying ? '重试中...' : '重试'}
                            </button>
                          ) : null}
                        </div>
                      </td> : null}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </DataTableShell>
        ) : null}
      </div>

      <DetailDrawer open={Boolean(detailTemplate)} title={detailTemplate?.label ?? '来源详情'} description="模板配置与采集入口" width="standard" onClose={() => setDetailTemplate(null)}>
        {detailTemplate ? (
          <div className="source-page__detail">
            <dl className="source-page__detailGrid">
              <DetailItem label="模板 ID" value={detailTemplate.id} />
              <DetailItem label="任务名称" value={detailTemplate.name} />
              <DetailItem label="起始地址" value={detailTemplate.startUrl} />
              <DetailItem label="定时表达式" value={detailTemplate.cronExpr} />
              <DetailItem label="模板说明" value={detailTemplate.description} />
              <DetailItem label="标签" value={detailTemplate.tags.join('、') || '无'} />
            </dl>
            <div className="source-page__dialogActions">
              <button className="source-page__secondaryButton" type="button" onClick={() => setDetailTemplate(null)}>
                关闭
              </button>
              {canManage ? (
                <button
                  className="source-page__primaryButton"
                  type="button"
                  onClick={() => {
                    setEditorTemplate(detailTemplate)
                    setDetailTemplate(null)
                  }}
                >
                  编辑模板
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </DetailDrawer>

      {canManage && (creating || editorTemplate) ? (
        <TemplateEditorDialog
          title={editorTemplate ? '编辑来源模板' : '新建来源模板'}
          template={editorTemplate}
          saving={saving}
          onClose={() => {
            if (!saving) {
              setCreating(false)
              setEditorTemplate(null)
            }
          }}
          onSubmit={handleSaveTemplate}
          onTest={async (payload) => client.post<TestTemplateResponse>('/v1/templates/test', payload)}
        />
      ) : null}

      {canManage && deleteTemplate ? (
        <ConfirmDialog
          title="确认删除模板"
          description={`删除后将移除“${deleteTemplate.label}”的模板配置。`}
          confirmLabel="确认删除"
          busy={pendingIds.includes(deleteTemplate.id)}
          onCancel={() => setDeleteTemplate(null)}
          onConfirm={() => void handleDeleteTemplate()}
        />
      ) : null}

      {canManage && collectTemplate ? (
        <ManualCollectDialog
          template={collectTemplate}
          pending={pendingIds.includes(collectTemplate.id)}
          onClose={() => setCollectTemplate(null)}
          onSubmit={async (url) => {
            markPending(collectTemplate.id, true)
            try {
              const result = await client.post<ManualCollectionResponse>(`/v1/templates/tasks/${collectTemplate.id}/collect`, {
                url,
              })
              setFeedback({ tone: 'success', message: `已登记到通知池 #${result.notice_id}` })
              setCollectTemplate(null)
            } catch (requestError) {
              setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
              throw requestError
            } finally {
              markPending(collectTemplate.id, false)
            }
          }}
        />
      ) : null}
    </section>
  )
}

function TemplateEditorDialog({
  title,
  template,
  saving,
  onClose,
  onSubmit,
  onTest,
}: {
  title: string
  template: TemplateModel | null
  saving: boolean
  onClose: () => void
  onSubmit: (value: TemplateEditorValue, template: TemplateModel | null) => Promise<void>
  onTest: (payload: { start_url: string; parser_rules: string | null }) => Promise<TestTemplateResponse>
}) {
  const [value, setValue] = useState<TemplateEditorValue>(() => ({
    label: template?.label ?? '',
    name: template?.name ?? '',
    startUrl: template?.startUrl ?? '',
    cronExpr: template?.cronExpr ?? '0 */6 * * *',
    parserRules: template?.parserRules ?? '',
    description: template?.description ?? '',
    tags: template?.tags.join(', ') ?? '',
    enabled: template?.enabled ?? true,
  }))
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!value.label.trim() || !value.name.trim() || !value.startUrl.trim() || !value.cronExpr.trim() || !value.description.trim()) {
      setError('请补全必填字段。')
      return
    }
    setError(null)
    try {
      await onSubmit(value, template)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  async function handleTest() {
    if (testing || saving) return
    if (!value.startUrl.trim()) {
      setError('请先填写起始地址。')
      return
    }
    setTesting(true)
    setError(null)
    try {
      const result = await onTest({
        start_url: value.startUrl.trim(),
        parser_rules: value.parserRules.trim() || null,
      })
      setTestResult(
        [
          result.title ?? '未提取到标题',
          `质量分：${result.quality_score ?? 0}`,
          result.content_text ?? '无正文预览',
          result.trace?.notes.join('；') ?? '',
        ]
          .filter(Boolean)
          .join('\n'),
      )
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setTesting(false)
    }
  }

  return (
    <DialogShell title={title} onClose={onClose}>
      <form className="source-page__dialogForm" onSubmit={(event) => void handleSubmit(event)}>
        <Field label="模板名称">
          <input value={value.label} onChange={(event) => setValue((current) => ({ ...current, label: event.target.value }))} />
        </Field>
        <Field label="任务名称">
          <input value={value.name} onChange={(event) => setValue((current) => ({ ...current, name: event.target.value }))} />
        </Field>
        <Field label="起始地址">
          <input value={value.startUrl} onChange={(event) => setValue((current) => ({ ...current, startUrl: event.target.value }))} />
        </Field>
        <Field label="定时表达式">
          <input value={value.cronExpr} onChange={(event) => setValue((current) => ({ ...current, cronExpr: event.target.value }))} />
        </Field>
        <Field label="解析规则 JSON">
          <textarea value={value.parserRules} onChange={(event) => setValue((current) => ({ ...current, parserRules: event.target.value }))} rows={4} />
        </Field>
        <Field label="模板说明">
          <textarea value={value.description} onChange={(event) => setValue((current) => ({ ...current, description: event.target.value }))} rows={3} />
        </Field>
        <Field label="标签">
          <input value={value.tags} onChange={(event) => setValue((current) => ({ ...current, tags: event.target.value }))} />
        </Field>
        <label className="source-page__checkRow">
          <input type="checkbox" checked={value.enabled} onChange={(event) => setValue((current) => ({ ...current, enabled: event.target.checked }))} />
          <span>默认启用</span>
        </label>
        {error ? (
          <div className="source-page__dialogError" role="alert">
            {error}
          </div>
        ) : null}
        {testResult ? <pre className="source-page__testResult">{testResult}</pre> : null}
        <div className="source-page__dialogActions">
          <button className="source-page__secondaryButton" type="button" onClick={() => void handleTest()} disabled={testing || saving}>
            {testing ? '测试中...' : '在线测试'}
          </button>
          <button className="source-page__secondaryButton" type="button" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button className="source-page__primaryButton" type="submit" disabled={saving || testing}>
            {saving ? '保存中...' : '保存模板'}
          </button>
        </div>
      </form>
    </DialogShell>
  )
}

function ManualCollectDialog({
  template,
  pending,
  onClose,
  onSubmit,
}: {
  template: TemplateModel
  pending: boolean
  onClose: () => void
  onSubmit: (url: string) => Promise<void>
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!url.startsWith('https://mp.weixin.qq.com/')) {
      setError('请输入有效的公众号文章链接。')
      return
    }
    setError(null)
    try {
      await onSubmit(url.trim())
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  return (
    <DialogShell title="登记公众号文章" onClose={onClose}>
      <form className="source-page__dialogForm" onSubmit={(event) => void handleSubmit(event)}>
        <p className="source-page__dialogHint">当前模板：{template.label}</p>
        <Field label="文章链接">
          <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://mp.weixin.qq.com/s/..." autoFocus />
        </Field>
        {error ? (
          <div className="source-page__dialogError" role="alert">
            {error}
          </div>
        ) : null}
        <div className="source-page__dialogActions">
          <button className="source-page__secondaryButton" type="button" onClick={onClose} disabled={pending}>
            取消
          </button>
          <button className="source-page__primaryButton" type="submit" disabled={pending}>
            {pending ? '登记中...' : '登记入库'}
          </button>
        </div>
      </form>
    </DialogShell>
  )
}

function StatCard({
  title,
  value,
  active,
  onClick,
}: {
  title: string
  value: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button className={`source-page__stat ${active ? 'source-page__stat--active' : ''}`} type="button" aria-label={title} onClick={onClick}>
      <span>{title}</span>
      <strong>{value}</strong>
    </button>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="source-page__field">
      <span className="source-page__fieldLabel">{label}</span>
      {children}
    </label>
  )
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value || '无'}</dd>
    </>
  )
}

function ConfirmDialog({
  title,
  description,
  confirmLabel,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string
  description: string
  confirmLabel: string
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <DialogShell title={title} onClose={onCancel}>
      <div className="source-page__detail">
        <p>{description}</p>
        <div className="source-page__dialogActions">
          <button className="source-page__secondaryButton" type="button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="source-page__primaryButton source-page__primaryButton--danger" type="button" onClick={onConfirm} disabled={busy}>
            {busy ? '处理中...' : confirmLabel}
          </button>
        </div>
      </div>
    </DialogShell>
  )
}

function DialogShell({
  title,
  children,
  onClose,
}: {
  title: string
  children: ReactNode
  onClose: () => void
}) {
  return (
    <div className="source-page__overlay" role="presentation" onClick={onClose}>
      <div
        className="source-page__dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}
      >
        <div className="source-page__dialogHeader">
          <h3>{title}</h3>
          <button className="source-page__ghostButton" type="button" aria-label="关闭弹窗" onClick={onClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

async function loadTemplateHealth(client: ReturnType<typeof useAuth>['client'], templates: TemplateModel[]) {
  const targetNames = new Set(templates.map((template) => template.name).filter(Boolean))
  const tasks = await fetchTasksByNames(client, targetNames)
  const healthByTemplateId: Record<string, TemplateHealth> = {}

  for (const template of templates) {
    const task = tasks.find((item) => item.name === template.name) ?? null
    let latestLog: LogModel | null = null
    if (task && ['failed', 'partial'].includes((task.lastRunStatus ?? '').toLowerCase())) {
      latestLog = await fetchLatestLog(client, task.id)
    }
    healthByTemplateId[template.id] = { task, latestLog }
  }

  return healthByTemplateId
}

async function fetchTasksByNames(client: ReturnType<typeof useAuth>['client'], names: Set<string>) {
  if (names.size === 0) return [] as TaskModel[]
  const matched = new Map<string, TaskModel>()
  let page = 1
  let total = 0
  do {
    const result = await client.get<TaskListResponse>('/v1/tasks', {
      query: {
        page,
        page_size: 100,
        sort_by: 'name',
        sort_dir: 'asc',
        enabled: 'all',
        last_run: 'all',
      },
    })
    total = result.total
    result.items.map(mapTask).forEach((task) => {
      if (names.has(task.name)) matched.set(task.name, task)
    })
    page += 1
  } while ((page - 1) * 100 < total && matched.size < names.size)
  return Array.from(matched.values())
}

async function fetchLatestLog(client: ReturnType<typeof useAuth>['client'], taskId: number) {
  const result = await client.get<LogListResponse>('/v1/logs', {
    query: {
      task_id: taskId,
      page: 1,
      page_size: 1,
    },
  })
  const [first] = result.items ?? []
  return first ? mapLog(first) : null
}

function resolveCollectionKind(template: TemplateModel): TemplateFilter {
  const parsed = tryParseRules(template.parserRules)
  const collectionMode = parsed?.collection_mode?.toString().trim().toLowerCase()
  const description = template.description.toLowerCase()
  if (collectionMode === 'manual' || manualTemplateIds.has(template.id)) return 'manual'
  if (authorizationTemplateIds.has(template.id) || description.includes('授权')) return 'needsAuth'
  return 'automatic'
}

function collectionKindLabel(kind: TemplateFilter) {
  if (kind === 'manual') return '人工登记'
  if (kind === 'needsAuth') return '授权来源'
  if (kind === 'automatic') return '自动采集'
  return '全部来源'
}

function resolveRuntimeStatus(template: TemplateModel, health: TemplateHealth) {
  const task = health.task
  const log = health.latestLog
  const kind = resolveCollectionKind(template)
  if (kind === 'manual') {
    return { label: '人工登记', note: '当前模板仅登记人工提供的文章链接，不执行自动抓取。', canRetry: false, tone: 'warm' as const }
  }
  if (kind === 'needsAuth') {
    return { label: '需授权', note: '当前来源依赖账号或平台授权，暂不自动运行。', canRetry: false, tone: 'warm' as const }
  }
  if (!task) {
    return { label: '待建任务', note: '模板已存在，但还没有关联到运行任务。', canRetry: false, tone: 'muted' as const }
  }
  const status = (task.lastRunStatus ?? '').toLowerCase()
  if (status === 'failed') {
    const failureText = log?.errorStack ?? task.lastErrorMessage ?? log?.message ?? '最近一次任务失败'
    return {
      label: '运行失败',
      note: looksLikeParseFailure(failureText) ? '解析规则需要调整，建议修正后重试。' : failureText,
      canRetry: true,
      tone: 'danger' as const,
    }
  }
  if (status === 'queued' || status === 'running') {
    return { label: '正在运行', note: '任务已进入执行队列，稍后刷新可查看结果。', canRetry: false, tone: 'info' as const }
  }
  if (status === 'success') {
    return { label: '运行正常', note: `最近成功：${formatDateTime(task.lastSuccessAt)}`, canRetry: false, tone: 'success' as const }
  }
  return { label: '等待首跑', note: '模板已配置，但还没有稳定的运行记录。', canRetry: false, tone: 'muted' as const }
}

function tryParseRules(raw: string | null) {
  if (!raw?.trim()) return null
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return null
  }
}

function looksLikeParseFailure(text: string) {
  const normalized = text.toLowerCase()
  return ['parse', 'selector', 'xpath', 'extract', 'content', '解析', '提取'].some((item) => normalized.includes(item))
}

function mapTemplate(dto: TemplateDto): TemplateModel {
  return {
    id: dto.id,
    label: dto.label,
    name: dto.name,
    startUrl: dto.start_url,
    cronExpr: dto.cron_expr,
    parserRules: dto.parser_rules,
    enabled: dto.enabled,
    description: dto.description,
    tags: dto.tags,
    usageCount: dto.usage_count,
    lastUsedAt: dto.last_used_at,
  }
}

function mapTask(dto: TaskDto): TaskModel {
  return {
    id: dto.id,
    name: dto.name,
    lastRunStatus: dto.last_run_status,
    lastRunAt: dto.last_run_at,
    lastSuccessAt: dto.last_success_at,
    lastErrorMessage: dto.last_error_message,
  }
}

function mapLog(dto: LogDto): LogModel {
  return {
    id: dto.id,
    taskId: dto.task_id,
    message: dto.message,
    errorStack: dto.error_stack,
    runSummary: dto.run_summary,
  }
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}

function formatDateTime(value: string | null) {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未记录'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

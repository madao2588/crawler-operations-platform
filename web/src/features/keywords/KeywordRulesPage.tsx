import { useEffect, useMemo, useState } from 'react'
import type { FormEvent, MouseEvent, ReactNode } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useAuth } from '../../auth/AuthProvider'
import { PageToolbar } from '../../components/UiPrimitives'
import './KeywordRulesPage.css'

type KeywordFilter = 'all' | 'enabled' | 'highPriority'

interface KeywordRuleDto {
  id: number
  word: string
  is_high_priority: boolean
  is_active: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

interface KeywordRule {
  id: number
  word: string
  isHighPriority: boolean
  isActive: boolean
  isDefault: boolean
  createdAt: string
  updatedAt: string
}

interface KeywordRuleList {
  items: KeywordRuleDto[]
  total: number
  default_total: number
  custom_total: number
}

interface RuleEditorState {
  mode: 'create' | 'edit'
  rule: KeywordRule | null
}

interface FeedbackState {
  tone: 'success' | 'error'
  message: string
}

const emptyRuleDraft = {
  word: '',
  isHighPriority: false,
  isActive: true,
}

export function KeywordRulesPage({ canManage: canManageProp }: { canManage?: boolean } = {}) {
  const { client, session } = useAuth()
  const canManage = canManageProp ?? session?.user.role !== 'user'
  const [rules, setRules] = useState<KeywordRule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<KeywordFilter>('all')
  const [editor, setEditor] = useState<RuleEditorState | null>(null)
  const [saving, setSaving] = useState(false)
  const [deletingRule, setDeletingRule] = useState<KeywordRule | null>(null)
  const [busyIds, setBusyIds] = useState<number[]>([])
  const [feedback, setFeedback] = useState<FeedbackState | null>(null)

  useEffect(() => {
    void refreshRules()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const visibleRules = useMemo(() => {
    if (filter === 'enabled') return rules.filter((rule) => rule.isActive)
    if (filter === 'highPriority') return rules.filter((rule) => rule.isHighPriority)
    return rules
  }, [filter, rules])

  const summary = useMemo(
    () => ({
      total: rules.length,
      enabled: rules.filter((rule) => rule.isActive).length,
      highPriority: rules.filter((rule) => rule.isHighPriority).length,
      defaults: rules.filter((rule) => rule.isDefault).length,
      custom: rules.filter((rule) => !rule.isDefault).length,
    }),
    [rules],
  )

  async function refreshRules() {
    setLoading(true)
    setError(null)
    try {
      const data = await client.get<KeywordRuleList>('/v1/keywords')
      setRules(data.items.map(mapRule))
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  function openCreateDialog() {
    if (!canManage) return
    setEditor({ mode: 'create', rule: null })
  }

  function openEditDialog(rule: KeywordRule) {
    if (!canManage) return
    setEditor({ mode: 'edit', rule })
  }

  async function handleSaveRule(draft: typeof emptyRuleDraft) {
    if (!canManage || saving) return
    setSaving(true)
    try {
      if (editor?.mode === 'create') {
        const created = await client.post<KeywordRuleDto>('/v1/keywords', {
          word: draft.word.trim(),
          is_high_priority: draft.isHighPriority,
          is_active: draft.isActive,
        })
        setRules((current) => [mapRule(created), ...current])
        setFeedback({ tone: 'success', message: '关键词规则已创建' })
      } else if (editor?.rule) {
        const updated = await client.put<KeywordRuleDto>(`/v1/keywords/${editor.rule.id}`, {
          word: draft.word.trim(),
          is_high_priority: draft.isHighPriority,
          is_active: draft.isActive,
        })
        setRules((current) => current.map((rule) => (rule.id === updated.id ? mapRule(updated) : rule)))
        setFeedback({ tone: 'success', message: '关键词规则已更新' })
      }
      setEditor(null)
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
      throw requestError
    } finally {
      setSaving(false)
    }
  }

  async function handleToggleActive(rule: KeywordRule) {
    if (!canManage) return
    const ruleId = rule.id
    if (busyIds.includes(ruleId)) return
    setBusyIds((current) => [...current, ruleId])
    try {
      const updated = await client.post<KeywordRuleDto>(`/v1/keywords/${ruleId}/toggle`)
      setRules((current) => current.map((item) => (item.id === ruleId ? mapRule(updated) : item)))
      setFeedback({
        tone: 'success',
        message: updated.is_active ? `${updated.word} 已启用` : `${updated.word} 已停用`,
      })
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
    } finally {
      setBusyIds((current) => current.filter((id) => id !== ruleId))
    }
  }

  async function handleDeleteRule() {
    if (!canManage || !deletingRule || deletingRule.isDefault || busyIds.includes(deletingRule.id)) return
    const ruleId = deletingRule.id
    const currentRule = deletingRule
    setBusyIds((current) => [...current, ruleId])
    try {
      await client.delete<{ success: boolean }>(`/v1/keywords/${ruleId}`)
      setRules((current) => current.filter((rule) => rule.id !== ruleId))
      setDeletingRule(null)
      setFeedback({ tone: 'success', message: `${currentRule.word} 已删除` })
    } catch (requestError) {
      setFeedback({ tone: 'error', message: getErrorMessage(requestError) })
    } finally {
      setBusyIds((current) => current.filter((id) => id !== ruleId))
    }
  }

  return (
    <section className="keyword-page">
      <PageToolbar
        title="规则维护"
        actions={
          <div className="keyword-page__heroActions">
          <button className="keyword-page__secondaryButton" type="button" onClick={() => void refreshRules()}>
            <RefreshCw aria-hidden="true" />
            刷新列表
          </button>
          {canManage ? (
            <button className="keyword-page__primaryButton" type="button" onClick={openCreateDialog}>
              <Plus aria-hidden="true" />
              新建规则
            </button>
          ) : null}
          </div>
        }
      />

      {feedback ? (
        <div className={`keyword-page__feedback keyword-page__feedback--${feedback.tone}`} role={feedback.tone === 'error' ? 'alert' : 'status'}>
          {feedback.message}
        </div>
      ) : null}
      {!canManage ? <p className="read-only-banner">普通用户为只读模式，可查看和筛选规则，修改请联系管理员。</p> : null}

      <div className="keyword-page__stats">
        <MetricCard
          title="规则总数"
          value={summary.total}
          active={filter === 'all'}
          onClick={() => setFilter('all')}
        />
        <MetricCard
          title="已启用"
          value={summary.enabled}
          active={filter === 'enabled'}
          onClick={() => setFilter('enabled')}
        />
        <MetricCard
          title="高优先级"
          value={summary.highPriority}
          active={filter === 'highPriority'}
          onClick={() => setFilter('highPriority')}
        />
      </div>

      <div className="keyword-page__panel">
        <div className="keyword-page__panelHeader">
          <h2>规则列表</h2>
          <span className="keyword-page__panelMeta">
            当前显示 {visibleRules.length} 条
            <span>系统默认 {summary.defaults} 条 · 自定义 {summary.custom} 条</span>
          </span>
        </div>

        {loading ? <div className="keyword-page__state">正在加载规则...</div> : null}
        {!loading && error ? (
          <div className="keyword-page__state keyword-page__state--error" role="alert">
            <p>{error}</p>
            <button className="keyword-page__secondaryButton" type="button" onClick={() => void refreshRules()}>
              重试加载
            </button>
          </div>
        ) : null}
        {!loading && !error && visibleRules.length === 0 ? (
          <div className="keyword-page__state">
            <p>{summary.total === 0 ? '还没有关键词规则。' : '当前筛选条件下没有规则。'}</p>
            {summary.total === 0 && !canManage ? null : (
              <button
                className={summary.total === 0 ? 'keyword-page__primaryButton' : 'keyword-page__secondaryButton'}
                type="button"
                onClick={summary.total === 0 ? openCreateDialog : () => setFilter('all')}
              >
                {summary.total === 0 ? <Plus aria-hidden="true" /> : null}
                {summary.total === 0 ? '新建第一条规则' : '清除筛选'}
              </button>
            )}
          </div>
        ) : null}
        {!loading && !error && visibleRules.length > 0 ? (
          <div
            className="keyword-page__tableWrap"
            role="region"
            aria-label="规则结果"
            data-scroll-region="table"
            tabIndex={0}
          >
            <table className="keyword-page__table">
              <thead>
                <tr>
                  <th scope="col">关键词</th>
                  <th scope="col">优先级</th>
                  <th scope="col">状态</th>
                  <th scope="col">更新时间</th>
                  {canManage ? <th scope="col">操作</th> : null}
                </tr>
              </thead>
              <tbody>
                {visibleRules.map((rule) => {
                  const busy = busyIds.includes(rule.id)
                  return (
                    <tr
                      key={rule.id}
                      className={`keyword-page__row ${rule.isDefault ? 'keyword-page__row--default' : ''}`}
                      onClick={canManage ? () => openEditDialog(rule) : undefined}
                      tabIndex={canManage ? 0 : -1}
                      onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            if (canManage) openEditDialog(rule)
                          }
                        }}
                    >
                      <td>
                        <div className="keyword-page__wordCell">
                          <strong>{rule.word}</strong>
                          {rule.isDefault ? <span className="keyword-page__sourceTag">系统默认</span> : null}
                          <button
                            className={`keyword-page__tag ${rule.isHighPriority ? 'keyword-page__tag--high' : ''}`}
                            type="button"
                            aria-label={`规则标签 ${rule.isHighPriority ? '高优先级' : '普通规则'} ${rule.word}`}
                            onClick={(event) => {
                              event.stopPropagation()
                              setFilter(rule.isHighPriority ? 'highPriority' : 'all')
                            }}
                          >
                            {rule.isHighPriority ? '高优先级' : '普通规则'}
                          </button>
                        </div>
                      </td>
                      <td>{rule.isHighPriority ? '命中即标记高优' : '仅普通命中'}</td>
                      <td>
                        {canManage ? (
                          <button
                            className={`keyword-page__toggle ${rule.isActive ? 'keyword-page__toggle--on' : 'keyword-page__toggle--off'}`}
                            type="button"
                            aria-label={`${rule.isActive ? '停用' : '启用'} ${rule.word}`}
                            onClick={(event) => {
                              event.stopPropagation()
                              void handleToggleActive(rule)
                            }}
                            disabled={busy}
                          >
                            {busy ? '处理中...' : rule.isActive ? '已启用' : '已停用'}
                          </button>
                        ) : (
                          <span className={`keyword-page__toggle ${rule.isActive ? 'keyword-page__toggle--on' : 'keyword-page__toggle--off'}`}>
                            {rule.isActive ? '已启用' : '已停用'}
                          </span>
                        )}
                      </td>
                      <td>{formatDateTime(rule.updatedAt)}</td>
                      {canManage ? <td>
                        <div className="keyword-page__actions">
                          <button
                            className="keyword-page__inlineButton"
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              openEditDialog(rule)
                            }}
                          >
                            编辑
                          </button>
                          {!rule.isDefault ? (
                            <button
                              className="keyword-page__inlineButton keyword-page__inlineButton--danger"
                              type="button"
                              aria-label={`删除 ${rule.word}`}
                              onClick={(event) => {
                                event.stopPropagation()
                                setDeletingRule(rule)
                              }}
                              disabled={busy}
                            >
                              删除
                            </button>
                          ) : null}
                        </div>
                      </td> : null}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {canManage && editor ? (
        <RuleEditorDialog
          title={editor.mode === 'create' ? '新建关键词规则' : '编辑关键词规则'}
          initialRule={
            editor.rule
              ? {
                  word: editor.rule.word,
                  isHighPriority: editor.rule.isHighPriority,
                  isActive: editor.rule.isActive,
                }
              : emptyRuleDraft
          }
          saving={saving}
          wordLocked={editor.rule?.isDefault ?? false}
          onClose={() => !saving && setEditor(null)}
          onSubmit={handleSaveRule}
        />
      ) : null}

      {canManage && deletingRule ? (
        <ConfirmDialog
          title="确认删除规则"
          description={`删除后无法恢复，确定要删除“${deletingRule.word}”吗？`}
          confirmLabel="确认删除"
          tone="danger"
          busy={busyIds.includes(deletingRule.id)}
          onCancel={() => setDeletingRule(null)}
          onConfirm={() => void handleDeleteRule()}
        />
      ) : null}
    </section>
  )
}

function RuleEditorDialog({
  title,
  initialRule,
  saving,
  wordLocked,
  onClose,
  onSubmit,
}: {
  title: string
  initialRule: typeof emptyRuleDraft
  saving: boolean
  wordLocked: boolean
  onClose: () => void
  onSubmit: (draft: typeof emptyRuleDraft) => Promise<void>
}) {
  const [word, setWord] = useState(initialRule.word)
  const [isHighPriority, setIsHighPriority] = useState(initialRule.isHighPriority)
  const [isActive, setIsActive] = useState(initialRule.isActive)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!word.trim()) {
      setError('关键词不能为空')
      return
    }
    setError(null)
    try {
      await onSubmit({
        word,
        isHighPriority,
        isActive,
      })
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  return (
    <DialogShell title={title} onClose={onClose}>
      <form className="keyword-page__dialogForm" onSubmit={(event) => void handleSubmit(event)}>
        <label className="keyword-page__field">
          <span>关键词</span>
          <input
            value={word}
            onChange={(event) => setWord(event.target.value)}
            disabled={saving || wordLocked}
            autoFocus={!wordLocked}
          />
        </label>
        {wordLocked ? (
          <p className="keyword-page__fieldHint">系统默认词不能改名或删除，但可以调整优先级和启用状态。</p>
        ) : null}
        <label className="keyword-page__checkRow">
          <input
            type="checkbox"
            checked={isHighPriority}
            onChange={(event) => setIsHighPriority(event.target.checked)}
            disabled={saving}
          />
          <span>高优先级</span>
        </label>
        <label className="keyword-page__checkRow">
          <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} disabled={saving} />
          <span>启用规则</span>
        </label>
        {error ? (
          <div className="keyword-page__dialogError" role="alert">
            {error}
          </div>
        ) : null}
        <div className="keyword-page__dialogActions">
          <button className="keyword-page__secondaryButton" type="button" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button className="keyword-page__primaryButton" type="submit" disabled={saving}>
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </DialogShell>
  )
}

function MetricCard({
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
    <button
      className={`keyword-page__metric ${active ? 'keyword-page__metric--active' : ''}`}
      type="button"
      aria-label={`筛选 ${title}`}
      onClick={onClick}
    >
      <span className="keyword-page__metricTitle">{title}</span>
      <strong className="keyword-page__metricValue">{value}</strong>
    </button>
  )
}

function ConfirmDialog({
  title,
  description,
  confirmLabel,
  tone,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string
  description: string
  confirmLabel: string
  tone: 'danger' | 'default'
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <DialogShell title={title} onClose={onCancel}>
      <div className="keyword-page__dialogBody">
        <p>{description}</p>
        <div className="keyword-page__dialogActions">
          <button className="keyword-page__secondaryButton" type="button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button
            className={`keyword-page__primaryButton ${tone === 'danger' ? 'keyword-page__primaryButton--danger' : ''}`}
            type="button"
            onClick={onConfirm}
            disabled={busy}
          >
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
    <div className="keyword-page__overlay" role="presentation" onClick={onClose}>
      <div
        className="keyword-page__dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}
      >
        <div className="keyword-page__dialogHeader">
          <h3>{title}</h3>
          <button className="keyword-page__ghostButton" type="button" aria-label="关闭弹窗" onClick={onClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function mapRule(dto: KeywordRuleDto): KeywordRule {
  return {
    id: dto.id,
    word: dto.word,
    isHighPriority: dto.is_high_priority,
    isActive: dto.is_active,
    isDefault: dto.is_default,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

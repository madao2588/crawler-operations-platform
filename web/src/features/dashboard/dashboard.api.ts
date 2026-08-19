import type {
  DashboardMetrics,
  DashboardCollectionHealth,
  DashboardOverview,
  DashboardRuntime,
  KeywordHeatItem,
  NoticeListItem,
  ProjectSignalItem,
  SourceDistributionItem,
} from './dashboard.types'
import type { ApiClient } from '../../api/client'

export const dashboardOverviewQueryKey = ['dashboard-overview'] as const

export async function fetchDashboardOverview(client: ApiClient): Promise<DashboardOverview> {
  const raw = await client.get<unknown>('/v1/dashboard/overview')
  return mapDashboardOverview(raw)
}

function mapDashboardOverview(raw: unknown): DashboardOverview {
  const record = asRecord(raw)
  return {
    metrics: mapMetrics(record.metrics),
    runtime: mapRuntime(record.runtime),
    collectionHealth: mapCollectionHealth(record.collection_health),
    highValueNotices: mapNoticeList(record.high_value_notices),
    recentNotices: mapNoticeList(record.recent_notices),
    keywordHeat: mapKeywordHeat(record.keyword_heat),
    sourceDistribution: mapSourceDistribution(record.source_distribution),
    projectSignalDistribution: mapProjectSignals(record.project_signal_distribution),
    lastUpdatedAt: asOptionalString(record.last_updated_at),
  }
}

function mapCollectionHealth(raw: unknown): DashboardCollectionHealth {
  const record = asRecord(raw)
  return {
    status: asString(record.status, 'idle'),
    monitoredTaskCount: asNumber(record.monitored_task_count),
    failedTaskCount: asNumber(record.failed_task_count),
    partialTaskCount: asNumber(record.partial_task_count),
    staleTaskCount: asNumber(record.stale_task_count),
    lastSuccessAt: asOptionalString(record.last_success_at),
    failedSources: Array.isArray(record.failed_sources)
      ? record.failed_sources.filter((item): item is string => typeof item === 'string')
      : [],
    partialSources: Array.isArray(record.partial_sources)
      ? record.partial_sources.filter((item): item is string => typeof item === 'string')
      : [],
    issues: Array.isArray(record.issues)
      ? record.issues.map((item) => {
          const issue = asRecord(item)
          return {
            taskId: asNumber(issue.task_id),
            taskName: asString(issue.task_name, '未命名采集任务'),
            status: asString(issue.status, 'failed'),
            reason: asString(issue.reason, '采集状态异常，请查看系统日志。'),
            isStale: Boolean(issue.is_stale),
            lastSuccessAt: asOptionalString(issue.last_success_at),
          }
        })
      : [],
  }
}

function mapMetrics(raw: unknown): DashboardMetrics {
  const record = asRecord(raw)
  return {
    todayNewNotices: asNumber(record.today_new_notices),
    keywordHitNotices: asNumber(record.keyword_hit_notices),
    monitoringSiteCount: asNumber(record.monitoring_site_count),
    highPriorityNotices: asNumber(record.high_priority_notices),
    highQualityNotices: asNumber(record.high_quality_notices),
    projectDeclarationNotices: asNumber(record.project_declaration_notices),
    resultPublicationNotices: asNumber(record.result_publication_notices),
  }
}

function mapRuntime(raw: unknown): DashboardRuntime {
  const record = asRecord(raw)
  return {
    status: asString(record.status, 'unknown'),
    database: asString(record.database, 'unknown'),
    scheduler: asString(record.scheduler, 'unknown'),
    scheduledJobs: asNumber(record.scheduled_jobs),
    releaseVersion: asString(record.release_version, 'dev'),
  }
}

function mapNoticeList(raw: unknown): NoticeListItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map(mapNotice)
}

function mapNotice(raw: unknown): NoticeListItem {
  const record = asRecord(raw)
  return {
    id: asNumber(record.id),
    title: asString(record.title),
    summary: asString(record.summary),
    sourceSite: asString(record.source_site),
    sourceUrl: asString(record.source_url),
    publishedAt: asOptionalString(record.published_at),
    capturedAt: asString(record.captured_at),
    qualityScore: asNumber(record.quality_score),
    matchedKeywords: Array.isArray(record.matched_keywords)
      ? record.matched_keywords.map((item) => asString(item)).filter(Boolean)
      : [],
    isHighPriority: Boolean(record.is_high_priority),
    projectSignal: asString(record.project_signal, '其他项目线索'),
    category: asString(record.category, '未分类'),
    aiSummary: asOptionalString(record.ai_summary),
    reviewStatus: asString(record.review_status, '待关注'),
    isArchived: Boolean(record.is_archived),
    remark: asOptionalString(record.remark),
    taskId: asNumber(record.task_id),
  }
}

function mapKeywordHeat(raw: unknown): KeywordHeatItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const record = asRecord(item)
    return {
      keyword: asString(record.keyword),
      count: asNumber(record.count),
    }
  })
}

function mapSourceDistribution(raw: unknown): SourceDistributionItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const record = asRecord(item)
    return {
      sourceSite: asString(record.source_site),
      displayName: asString(record.display_name, asString(record.source_site)),
      noticeCount: asNumber(record.notice_count),
      percentage: asNumber(record.percentage),
    }
  })
}

function mapProjectSignals(raw: unknown): ProjectSignalItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const record = asRecord(item)
    return {
      label: asString(record.label),
      noticeCount: asNumber(record.notice_count),
      percentage: asNumber(record.percentage),
    }
  })
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asOptionalString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function asNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

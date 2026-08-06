export interface DashboardMetrics {
  todayNewNotices: number
  keywordHitNotices: number
  monitoringSiteCount: number
  highPriorityNotices: number
  highQualityNotices: number
  projectDeclarationNotices: number
  resultPublicationNotices: number
}

export interface DashboardRuntime {
  status: string
  database: string
  scheduler: string
  scheduledJobs: number
}

export interface NoticeListItem {
  id: number
  title: string
  summary: string
  sourceSite: string
  sourceUrl: string
  publishedAt: string | null
  capturedAt: string
  qualityScore: number
  matchedKeywords: string[]
  isHighPriority: boolean
  projectSignal: string
  category: string
  aiSummary: string | null
  reviewStatus: string
  isArchived: boolean
  remark: string | null
  taskId: number
}

export interface KeywordHeatItem {
  keyword: string
  count: number
}

export interface SourceDistributionItem {
  sourceSite: string
  displayName: string
  noticeCount: number
  percentage: number
}

export interface ProjectSignalItem {
  label: string
  noticeCount: number
  percentage: number
}

export interface DashboardOverview {
  metrics: DashboardMetrics
  runtime: DashboardRuntime
  highValueNotices: NoticeListItem[]
  recentNotices: NoticeListItem[]
  keywordHeat: KeywordHeatItem[]
  sourceDistribution: SourceDistributionItem[]
  projectSignalDistribution: ProjectSignalItem[]
  lastUpdatedAt: string | null
}

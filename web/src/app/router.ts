import { useCallback, useSyncExternalStore } from 'react'

export const appPaths = ['/', '/notices', '/keywords', '/sources', '/system', '/login'] as const
export type AppPath = (typeof appPaths)[number]

export interface NoticeQuery {
  keyword?: string
  month?: string
  category?: string
  reviewStatus?: string
  archived?: boolean
  capturedToday?: boolean
  sourceSite?: string
  keywordHit?: boolean
  highPriority?: boolean
  highQuality?: boolean
  projectSignal?: string
  noticeId?: number
}

export interface AppLocation {
  path: AppPath
  search: string
}

const routeEvent = 'crawler:navigate'

export function normalizePath(pathname: string): AppPath {
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  return (appPaths as readonly string[]).includes(clean) ? (clean as AppPath) : '/'
}

export function buildNoticeUrl(query: NoticeQuery = {}) {
  const params = new URLSearchParams()
  setString(params, 'keyword', query.keyword)
  setMonth(params, query.month)
  setString(params, 'category', query.category)
  setString(params, 'review_status', query.reviewStatus)
  setBoolean(params, 'archived', query.archived)
  setBoolean(params, 'captured_today', query.capturedToday)
  setString(params, 'source_site', query.sourceSite)
  setBoolean(params, 'keyword_hit', query.keywordHit)
  setBoolean(params, 'high_priority', query.highPriority)
  setBoolean(params, 'high_quality', query.highQuality)
  setString(params, 'project_signal', query.projectSignal)
  if (query.noticeId !== undefined) params.set('notice_id', String(query.noticeId))
  const search = params.toString()
  return search ? `/notices?${search}` : '/notices'
}

export function readNoticeQuery(search: string): NoticeQuery {
  const params = new URLSearchParams(search)
  const result: NoticeQuery = {}
  assignString(result, 'keyword', params.get('keyword'))
  assignMonth(result, params.get('month'))
  assignString(result, 'category', params.get('category'))
  assignString(result, 'reviewStatus', params.get('review_status'))
  assignBoolean(result, 'archived', params.get('archived'))
  assignBoolean(result, 'capturedToday', params.get('captured_today'))
  assignString(result, 'sourceSite', params.get('source_site'))
  assignBoolean(result, 'keywordHit', params.get('keyword_hit'))
  assignBoolean(result, 'highPriority', params.get('high_priority'))
  assignBoolean(result, 'highQuality', params.get('high_quality'))
  assignString(result, 'projectSignal', params.get('project_signal'))
  const noticeId = Number(params.get('notice_id'))
  if (Number.isInteger(noticeId) && noticeId > 0) result.noticeId = noticeId
  return result
}

export function navigate(to: string, options: { replace?: boolean } = {}) {
  if (options.replace) window.history.replaceState(null, '', to)
  else window.history.pushState(null, '', to)
  window.dispatchEvent(new Event(routeEvent))
}

export function useAppLocation(): AppLocation {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

export function useNavigate() {
  return useCallback((to: string, options?: { replace?: boolean }) => navigate(to, options), [])
}

function subscribe(onStoreChange: () => void) {
  window.addEventListener('popstate', onStoreChange)
  window.addEventListener(routeEvent, onStoreChange)
  return () => {
    window.removeEventListener('popstate', onStoreChange)
    window.removeEventListener(routeEvent, onStoreChange)
  }
}

let cachedHref = ''
let cachedLocation: AppLocation = { path: '/', search: '' }

function getSnapshot(): AppLocation {
  const href = window.location.href
  if (href !== cachedHref) {
    cachedHref = href
    cachedLocation = {
      path: normalizePath(window.location.pathname),
      search: window.location.search,
    }
  }
  return cachedLocation
}

function getServerSnapshot(): AppLocation {
  return { path: '/', search: '' }
}

function setString(params: URLSearchParams, key: string, value?: string) {
  if (value?.trim()) params.set(key, value.trim())
}

function setBoolean(params: URLSearchParams, key: string, value?: boolean) {
  if (value !== undefined) params.set(key, String(value))
}

const noticeMonthPattern = /^\d{4}-(0[1-9]|1[0-2])$/

function setMonth(params: URLSearchParams, value?: string) {
  if (value && noticeMonthPattern.test(value)) params.set('month', value)
}

function assignString<T extends object, K extends keyof T>(target: T, key: K, value: string | null) {
  if (value) target[key] = value as T[K]
}

function assignBoolean<T extends object, K extends keyof T>(target: T, key: K, value: string | null) {
  if (value === 'true' || value === 'false') target[key] = (value === 'true') as T[K]
}

function assignMonth(target: NoticeQuery, value: string | null) {
  if (value && noticeMonthPattern.test(value)) target.month = value
}

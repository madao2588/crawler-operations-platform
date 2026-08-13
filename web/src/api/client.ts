export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

export type QueryValue = string | number | boolean | null | undefined

interface ApiClientOptions {
  baseUrl?: string
  fetcher?: typeof fetch
  getToken?: () => string | null
  onUnauthorized?: () => void | Promise<void>
  timeoutMs?: number
}

interface RequestOptions {
  query?: Record<string, QueryValue>
  body?: unknown
  signal?: AbortSignal
}

export class ApiError extends Error {
  readonly status: number | null
  readonly code: number | null
  readonly data: unknown

  constructor(
    message: string,
    options: { status?: number; code?: number; data?: unknown } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? null
    this.code = options.code ?? null
    this.data = options.data ?? null
  }
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof fetch
  private readonly getToken: () => string | null
  private readonly onUnauthorized?: () => void | Promise<void>
  private readonly timeoutMs: number
  private handlingUnauthorized = false
  private unauthorizedToken: string | null = null

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl?.replace(/\/$/, '') ?? import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
    this.fetcher = options.fetcher ?? fetch.bind(window)
    this.getToken = options.getToken ?? (() => null)
    this.onUnauthorized = options.onUnauthorized
    this.timeoutMs = options.timeoutMs ?? 15_000
  }

  get<T>(path: string, options: Omit<RequestOptions, 'body'> = {}) {
    return this.request<T>('GET', path, options)
  }

  post<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'body'> = {}) {
    return this.request<T>('POST', path, { ...options, body })
  }

  put<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'body'> = {}) {
    return this.request<T>('PUT', path, { ...options, body })
  }

  patch<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'body'> = {}) {
    return this.request<T>('PATCH', path, { ...options, body })
  }

  delete<T>(path: string, options: Omit<RequestOptions, 'body'> = {}) {
    return this.request<T>('DELETE', path, options)
  }

  private async request<T>(
    method: string,
    path: string,
    options: RequestOptions,
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`, window.location.origin)
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== null && value !== undefined && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }

    const headers: Record<string, string> = { Accept: 'application/json' }
    const token = this.getToken()
    if (token) headers.Authorization = `Bearer ${token}`
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'

    const timeoutController = new AbortController()
    const timeout = window.setTimeout(() => timeoutController.abort(), this.timeoutMs)
    const signal = options.signal
      ? AbortSignal.any([options.signal, timeoutController.signal])
      : timeoutController.signal

    let response: Response
    try {
      response = await this.fetcher(url.pathname + url.search, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal,
      })
    } catch (error) {
      if (timeoutController.signal.aborted && !options.signal?.aborted) {
        throw new ApiError(
          `请求超时（${method} ${url.pathname}，超过 ${Math.round(this.timeoutMs / 1000)} 秒）：后端仍在处理或暂时无响应，请稍后重试。`,
        )
      }
      if (error instanceof ApiError) throw error
      throw new ApiError(
        `无法连接后端（${method} ${url.pathname}）：服务未响应。请确认 npm start 正在运行后重试。`,
      )
    } finally {
      window.clearTimeout(timeout)
    }

    const payload = await this.parseResponse<T>(response)
    if (!response.ok || payload.code !== 0) {
      if (response.status === 401 && path !== '/v1/auth/login' && token) {
        await this.notifyUnauthorized(token)
      }
      throw new ApiError(payload.message || `请求失败（${response.status}）`, {
        status: response.status,
        code: payload.code,
        data: payload.data,
      })
    }
    if (payload.data === null) {
      throw new ApiError('服务器返回的数据为空。', {
        status: response.status,
        code: payload.code,
      })
    }
    return payload.data
  }

  private async parseResponse<T>(response: Response): Promise<ApiResponse<T>> {
    try {
      const payload: unknown = await response.json()
      if (
        typeof payload !== 'object' ||
        payload === null ||
        typeof (payload as Partial<ApiResponse<T>>).code !== 'number' ||
        typeof (payload as Partial<ApiResponse<T>>).message !== 'string' ||
        !('data' in payload)
      ) {
        throw new Error('invalid envelope')
      }
      return payload as ApiResponse<T>
    } catch {
      throw new ApiError('服务器返回了无法识别的数据。', { status: response.status })
    }
  }

  private async notifyUnauthorized(token: string) {
    if (!this.onUnauthorized || this.handlingUnauthorized || this.unauthorizedToken === token) return
    this.unauthorizedToken = token
    this.handlingUnauthorized = true
    try {
      await this.onUnauthorized()
    } finally {
      this.handlingUnauthorized = false
    }
  }
}

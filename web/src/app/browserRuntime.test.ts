import { describe, expect, it, vi } from 'vitest'
import { prepareBrowserRuntime } from './browserRuntime'

function createSessionStorage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  }
}

describe('prepareBrowserRuntime', () => {
  it('removes a legacy Flutter worker and its caches before reloading once', async () => {
    const unregister = vi.fn().mockResolvedValue(true)
    const deleteCache = vi.fn().mockResolvedValue(true)
    const reload = vi.fn()
    const sessionStorage = createSessionStorage()

    const shouldRender = await prepareBrowserRuntime({
      serviceWorkers: {
        controller: { scriptURL: 'http://127.0.0.1:8093/flutter_service_worker.js' },
        getRegistrations: vi.fn().mockResolvedValue([
          {
            active: { scriptURL: 'http://127.0.0.1:8093/flutter_service_worker.js' },
            unregister,
          },
        ]),
      },
      cacheStorage: {
        keys: vi.fn().mockResolvedValue(['flutter-app-cache', 'react-unrelated-cache']),
        delete: deleteCache,
      },
      sessionStorage,
      reload,
    })

    expect(unregister).toHaveBeenCalledOnce()
    expect(deleteCache).toHaveBeenCalledWith('flutter-app-cache')
    expect(deleteCache).not.toHaveBeenCalledWith('react-unrelated-cache')
    expect(reload).toHaveBeenCalledOnce()
    expect(shouldRender).toBe(false)
  })

  it('does not enter a reload loop when a legacy controller survives the first refresh', async () => {
    const reload = vi.fn()
    const sessionStorage = createSessionStorage()
    sessionStorage.setItem('react-migration:flutter-worker-reload', '1')

    const shouldRender = await prepareBrowserRuntime({
      serviceWorkers: {
        controller: { scriptURL: 'http://127.0.0.1:8093/flutter_service_worker.js' },
        getRegistrations: vi.fn().mockResolvedValue([]),
      },
      sessionStorage,
      reload,
    })

    expect(reload).not.toHaveBeenCalled()
    expect(shouldRender).toBe(true)
  })

  it('leaves unrelated workers and caches untouched', async () => {
    const unregister = vi.fn().mockResolvedValue(true)
    const deleteCache = vi.fn().mockResolvedValue(true)

    const shouldRender = await prepareBrowserRuntime({
      serviceWorkers: {
        controller: null,
        getRegistrations: vi.fn().mockResolvedValue([
          {
            active: { scriptURL: 'http://127.0.0.1:8093/react-service-worker.js' },
            unregister,
          },
        ]),
      },
      cacheStorage: {
        keys: vi.fn().mockResolvedValue(['react-app-cache']),
        delete: deleteCache,
      },
      sessionStorage: createSessionStorage(),
    })

    expect(unregister).not.toHaveBeenCalled()
    expect(deleteCache).not.toHaveBeenCalled()
    expect(shouldRender).toBe(true)
  })
})

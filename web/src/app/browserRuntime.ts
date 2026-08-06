const FLUTTER_WORKER_FILE = '/flutter_service_worker.js'
const FLUTTER_CACHE_PREFIX = 'flutter-'
const RELOAD_MARKER = 'react-migration:flutter-worker-reload'

interface WorkerLike {
  scriptURL: string
}

interface WorkerRegistrationLike {
  active?: WorkerLike | null
  installing?: WorkerLike | null
  waiting?: WorkerLike | null
  unregister: () => Promise<boolean>
}

interface ServiceWorkersLike {
  controller?: WorkerLike | null
  getRegistrations: () => Promise<readonly WorkerRegistrationLike[]>
}

interface CacheStorageLike {
  keys: () => Promise<string[]>
  delete: (cacheName: string) => Promise<boolean>
}

interface SessionStorageLike {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
  removeItem: (key: string) => void
}

interface BrowserRuntimeDependencies {
  serviceWorkers?: ServiceWorkersLike | null
  cacheStorage?: CacheStorageLike | null
  sessionStorage?: SessionStorageLike | null
  reload?: () => void
}

export async function prepareBrowserRuntime(
  dependencies: BrowserRuntimeDependencies = browserDependencies(),
): Promise<boolean> {
  const { serviceWorkers, cacheStorage, sessionStorage } = dependencies
  if (!serviceWorkers) return true

  try {
    const registrations = await serviceWorkers.getRegistrations()
    const flutterRegistrations = registrations.filter(isFlutterRegistration)
    const controlledByFlutter = isFlutterWorker(serviceWorkers.controller)

    await Promise.all(flutterRegistrations.map((registration) => registration.unregister()))

    if ((flutterRegistrations.length > 0 || controlledByFlutter) && cacheStorage) {
      const cacheNames = await cacheStorage.keys()
      await Promise.all(
        cacheNames
          .filter((cacheName) => cacheName.startsWith(FLUTTER_CACHE_PREFIX))
          .map((cacheName) => cacheStorage.delete(cacheName)),
      )
    }

    if (controlledByFlutter && sessionStorage?.getItem(RELOAD_MARKER) !== '1') {
      sessionStorage?.setItem(RELOAD_MARKER, '1')
      const reload = dependencies.reload ?? (() => window.location.reload())
      reload()
      return false
    }

    if (!controlledByFlutter) sessionStorage?.removeItem(RELOAD_MARKER)
    return true
  } catch {
    // Cleanup is best-effort. A browser storage error must not prevent the app from loading.
    return true
  }
}

function isFlutterRegistration(registration: WorkerRegistrationLike) {
  return [registration.active, registration.installing, registration.waiting].some(isFlutterWorker)
}

function isFlutterWorker(worker: WorkerLike | null | undefined) {
  if (!worker) return false
  try {
    return new URL(worker.scriptURL, window.location.origin).pathname.endsWith(FLUTTER_WORKER_FILE)
  } catch {
    return worker.scriptURL.includes('flutter_service_worker.js')
  }
}

function browserDependencies(): BrowserRuntimeDependencies {
  return {
    serviceWorkers: 'serviceWorker' in navigator ? navigator.serviceWorker : null,
    cacheStorage: 'caches' in window ? window.caches : null,
    sessionStorage: window.sessionStorage,
  }
}

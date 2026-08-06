import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from './App'
import { prepareBrowserRuntime } from './app/browserRuntime'
import { AuthProvider } from './auth/AuthProvider'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 0 },
  },
})

async function bootstrap() {
  const shouldRender = await prepareBrowserRuntime()
  if (!shouldRender) return

  const rootElement = document.getElementById('root')
  if (!rootElement) throw new Error('Missing application root element')

  createRoot(rootElement).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </QueryClientProvider>
    </StrictMode>,
  )
}

void bootstrap()

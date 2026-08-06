import type { PropsWithChildren, ReactNode } from 'react'

export function LoadingState({ label = '正在加载数据…' }: { label?: string }) {
  return <div className="state-panel" role="status"><span className="spinner" aria-hidden="true" /><p>{label}</p></div>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-panel error-state" role="alert">
      <strong>加载失败</strong>
      <p>{message}</p>
      {onRetry ? <button className="secondary-button" type="button" onClick={onRetry}>重新加载</button> : null}
    </div>
  )
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="state-panel empty-state"><strong>{title}</strong><p>{description}</p>{action}</div>
}

export function SectionCard({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`section-card ${className}`.trim()}>{children}</section>
}

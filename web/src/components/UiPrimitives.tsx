import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { PropsWithChildren, ReactNode } from 'react'

export function PageToolbar({
  kicker,
  title,
  description,
  actions,
}: {
  kicker?: string
  title?: string
  description?: string
  actions?: ReactNode
}) {
  if (!title && !description && !actions) return null
  return (
    <header className="page-toolbar">
      <div className="page-toolbar__copy">
        {kicker ? <p className="page-toolbar__kicker">{kicker}</p> : null}
        {title ? <h2>{title}</h2> : null}
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-toolbar__actions">{actions}</div> : null}
    </header>
  )
}

export interface MetricStripItem {
  key: string
  label: string
  value: ReactNode
  hint?: string
  active?: boolean
  onClick?: () => void
}

export function MetricStrip({ ariaLabel, items }: { ariaLabel: string; items: MetricStripItem[] }) {
  return (
    <div className="metric-strip" aria-label={ariaLabel}>
      {items.map((item) => {
        const content = (
          <>
            <span className="metric-strip__label">{item.label}</span>
            <strong className="metric-strip__value">{item.value}</strong>
            {item.hint ? <span className="metric-strip__hint">{item.hint}</span> : null}
          </>
        )
        return item.onClick ? (
          <button
            key={item.key}
            type="button"
            className={`metric-strip__item ${item.active ? 'is-active' : ''}`}
            aria-label={`${item.label} ${item.value}`}
            aria-pressed={Boolean(item.active)}
            onClick={item.onClick}
          >
            {content}
          </button>
        ) : (
          <div key={item.key} className="metric-strip__item">
            {content}
          </div>
        )
      })}
    </div>
  )
}

export function Panel({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`ui-panel ${className}`.trim()}>{children}</section>
}

export function DataTableShell({
  children,
  className = '',
  ariaLabel,
}: PropsWithChildren<{ className?: string; ariaLabel: string }>) {
  return (
    <div
      className={`data-table-shell ${className}`.trim()}
      role="region"
      aria-label={ariaLabel}
      data-scroll-region="table"
      tabIndex={0}
    >
      {children}
    </div>
  )
}

export function DetailDrawer({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  width = 'standard',
}: PropsWithChildren<{
  open: boolean
  title: string
  description?: string
  onClose: () => void
  footer?: ReactNode
  width?: 'compact' | 'standard' | 'wide'
}>) {
  const panelRef = useRef<HTMLElement>(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!open) return undefined
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', handleKeyDown)
    const frame = window.requestAnimationFrame(() => panelRef.current?.focus())
    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('keydown', handleKeyDown)
      previousFocus?.focus()
    }
  }, [open])

  if (!open) return null

  return (
    <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
      <section
        ref={panelRef}
        className={`detail-drawer detail-drawer--${width}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="detail-drawer__header">
          <div>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button className="icon-button" type="button" aria-label={`关闭${title}`} onClick={onClose}>
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="detail-drawer__body">{children}</div>
        {footer ? <footer className="detail-drawer__footer">{footer}</footer> : null}
      </section>
    </div>
  )
}

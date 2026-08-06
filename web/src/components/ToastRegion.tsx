import { useEffect } from 'react'

export interface ToastMessage {
  id: number
  tone: 'success' | 'error' | 'info'
  text: string
}

export function ToastRegion({ messages, onDismiss }: { messages: ToastMessage[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toast-region" aria-live="polite" aria-atomic="false">
      {messages.map((message) => <Toast key={message.id} message={message} onDismiss={onDismiss} />)}
    </div>
  )
}

function Toast({ message, onDismiss }: { message: ToastMessage; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(message.id), 4500)
    return () => window.clearTimeout(timer)
  }, [message.id, onDismiss])
  return <div className={`toast toast-${message.tone}`}><span>{message.text}</span><button type="button" aria-label="关闭提示" onClick={() => onDismiss(message.id)}>×</button></div>
}

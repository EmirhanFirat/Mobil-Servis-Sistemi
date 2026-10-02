import type { ReactNode } from 'react'

import { ApiError, NetworkError } from '../lib/api'
import { API_URL } from '../lib/config'

export function Loading({ message = 'Yükleniyor…' }: { message?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <p className="muted">{message}</p>
    </div>
  )
}

export function Empty({ title, message }: { title: string; message?: string }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  )
}

function describe(error: Error): { title: string; showServer: boolean } {
  if (error instanceof NetworkError) return { title: 'Bağlantı sorunu', showServer: true }
  if (error instanceof ApiError && error.status === 404) return { title: 'Bulunamadı', showServer: false }
  if (error instanceof ApiError && error.status === 403) return { title: 'Erişim yok', showServer: false }
  return { title: 'Bir sorun oluştu', showServer: false }
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { title, showServer } = describe(error)
  return (
    <div className="state" role="alert">
      <h3>{title}</h3>
      <p className="muted">{error.message}</p>
      {showServer ? <p className="muted">Sunucu: {API_URL}</p> : null}
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          Tekrar dene
        </button>
      ) : null}
    </div>
  )
}

export function Notice({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'error' | 'success'
  children: ReactNode
}) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}

export function Badge({ kind, children }: { kind?: string; children: ReactNode }) {
  return <span className={`badge ${kind ? `badge-${kind}` : ''}`}>{children}</span>
}

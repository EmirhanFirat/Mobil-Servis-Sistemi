import { useCallback } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Badge, Empty, ErrorBox, Loading, Notice } from '../components/ui'
import { useSession } from '../lib/auth-context'
import { formatDateTime, labelOf, ticketNumber } from '../lib/format'
import type { TicketStatus } from '../lib/types'
import { useResource } from '../lib/use-resource'

const PAGE_SIZE = 25

interface View {
  key: string
  label: string
  statuses: TicketStatus[]
}

const VIEWS: View[] = [
  { key: 'pending', label: 'Yönlendirme bekleyen', statuses: ['new', 'needs_review'] },
  { key: 'active', label: 'Ekipte', statuses: ['assigned', 'in_progress'] },
  { key: 'resolved', label: 'Çözüldü', statuses: ['resolved'] },
  { key: 'closed', label: 'Kapatıldı', statuses: ['closed'] },
  { key: 'all', label: 'Tümü', statuses: [] },
]

export default function TicketsPage() {
  const { api, vocab } = useSession()
  const [params, setParams] = useSearchParams()
  const view = VIEWS.find((item) => item.key === params.get('gorunum')) ?? VIEWS[0]
  const page = Math.max(1, Number(params.get('sayfa')) || 1)

  const load = useCallback(
    () =>
      api.listTickets({
        status: view.statuses.length > 0 ? view.statuses : undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
    [api, view, page],
  )
  const { data, error, loading, retry } = useResource(load)

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  function go(next: { gorunum?: string; sayfa?: number }) {
    const merged = new URLSearchParams(params)
    if (next.gorunum !== undefined) {
      merged.set('gorunum', next.gorunum)
      merged.delete('sayfa')
    }
    if (next.sayfa !== undefined) merged.set('sayfa', String(next.sayfa))
    setParams(merged)
  }

  return (
    <>
      <div className="page-head">
        <h1>Talepler</h1>
        <div className="tabs" role="tablist" aria-label="Talep görünümü">
          {VIEWS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={item.key === view.key}
              className={item.key === view.key ? 'tab active' : 'tab'}
              onClick={() => go({ gorunum: item.key })}>
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {loading && !data ? (
        <Loading message="Talepler yükleniyor…" />
      ) : error && !data ? (
        <ErrorBox error={error} onRetry={retry} />
      ) : data && data.items.length === 0 ? (
        <Empty
          title="Bu görünümde talep yok"
          message={
            view.key === 'pending'
              ? 'Yönlendirilmeyi bekleyen talep kalmadı.'
              : 'Başka bir görünüm seçmeyi dene.'
          }
        />
      ) : data ? (
        <>
          {error ? <Notice tone="error">Liste yenilenemedi: {error.message}</Notice> : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>No</th>
                  <th>Başlık</th>
                  <th>Konum</th>
                  <th>Durum</th>
                  <th>Öncelik</th>
                  <th>Kategori</th>
                  <th>Ekip</th>
                  <th>Görevli</th>
                  <th>Açılış</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((ticket) => (
                  <tr key={ticket.id}>
                    <td className="nowrap">{ticketNumber(ticket.number)}</td>
                    <td>
                      <Link to={`/talepler/${ticket.id}`}>{ticket.title}</Link>
                      <div className="muted small">{ticket.created_by.display_name}</div>
                    </td>
                    <td>{ticket.location}</td>
                    <td>
                      <Badge kind={ticket.status}>{labelOf(vocab.statuses, ticket.status)}</Badge>
                    </td>
                    <td>
                      <Badge kind={`priority-${ticket.priority}`}>
                        {labelOf(vocab.priorities, ticket.priority)}
                      </Badge>
                    </td>
                    <td>{labelOf(vocab.categories, ticket.category) || '—'}</td>
                    <td>{ticket.team ? labelOf(vocab.teams, ticket.team.code) : '—'}</td>
                    <td>{ticket.assignee?.display_name ?? '—'}</td>
                    <td className="nowrap">{formatDateTime(ticket.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span className="muted">
              Toplam {data.total} talep · Sayfa {page} / {totalPages}
            </span>
            <div className="row">
              <button
                type="button"
                className="btn"
                disabled={page <= 1}
                onClick={() => go({ sayfa: page - 1 })}>
                Önceki
              </button>
              <button
                type="button"
                className="btn"
                disabled={page >= totalPages}
                onClick={() => go({ sayfa: page + 1 })}>
                Sonraki
              </button>
            </div>
          </div>
        </>
      ) : null}
    </>
  )
}

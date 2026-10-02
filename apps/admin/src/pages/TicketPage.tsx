import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router'

import { DecisionCard } from '../components/DecisionCard'
import {
  AssignPanel,
  CorrectionPanel,
  History,
  TransitionPanel,
} from '../components/ticket-panels'
import { Badge, ErrorBox, Loading, Notice } from '../components/ui'
import { useSession } from '../lib/auth-context'
import { formatDateTime, labelOf, ticketNumber } from '../lib/format'
import type { TicketDetail } from '../lib/types'
import { useResource } from '../lib/use-resource'

export default function TicketPage() {
  const { id = '' } = useParams()
  const { api, vocab } = useSession()

  const loadTicket = useCallback(() => api.getTicket(id), [api, id])
  const loadTeams = useCallback(() => api.listTeams(), [api])
  const ticket = useResource(loadTicket)
  const teams = useResource(loadTeams)
  const [flash, setFlash] = useState<string | null>(null)

  const back = (
    <Link to="/" className="back">
      ← Taleplere dön
    </Link>
  )

  if ((ticket.loading && !ticket.data) || (teams.loading && !teams.data)) {
    return (
      <>
        {back}
        <Loading message="Talep yükleniyor…" />
      </>
    )
  }
  const failure = (ticket.error && !ticket.data ? ticket.error : null) ?? (teams.error && !teams.data ? teams.error : null)
  if (failure || !ticket.data || !teams.data) {
    return (
      <>
        {back}
        <ErrorBox
          error={failure ?? new Error('Talep yüklenemedi.')}
          onRetry={() => {
            void ticket.retry()
            void teams.retry()
          }}
        />
      </>
    )
  }

  const data = ticket.data
  // Panel durumları, sunucudan gelen güncel talep değişince sıfırlansın diye anahtarlanır.
  const panelKey = data.updated_at

  async function reload(message?: string) {
    await Promise.all([ticket.reload(), teams.reload()])
    setFlash(message ?? null)
  }

  return (
    <>
      {back}
      {flash ? <Notice tone="success">{flash}</Notice> : null}
      {ticket.error ? <Notice tone="error">Talep yenilenemedi: {ticket.error.message}</Notice> : null}
      <div className="page-head">
        <h1>
          <span className="muted">{ticketNumber(data.number)}</span> {data.title}
        </h1>
        <div className="row wrap">
          <Badge kind={data.status}>{labelOf(vocab.statuses, data.status)}</Badge>
          <Badge kind={`priority-${data.priority}`}>
            Öncelik: {labelOf(vocab.priorities, data.priority)}
          </Badge>
          {data.category ? <Badge>{labelOf(vocab.categories, data.category)}</Badge> : null}
          {data.review_required ? <Badge kind="needs_review">İnceleme gerekiyor</Badge> : null}
        </div>
      </div>

      <div className="columns">
        <div className="stack">
          <Details ticket={data} />
          <DecisionCard panel={data.decision} vocab={vocab} />
          <History ticket={data} vocab={vocab} />
        </div>
        <div className="stack">
          <TransitionPanel key={`t-${panelKey}`} ticket={data} api={api} onChanged={reload} />
          <AssignPanel
            key={`a-${panelKey}`}
            ticket={data}
            teams={teams.data}
            vocab={vocab}
            api={api}
            onChanged={reload}
          />
          <CorrectionPanel key={`c-${panelKey}`} ticket={data} vocab={vocab} api={api} onChanged={reload} />
        </div>
      </div>
    </>
  )
}

function Details({ ticket }: { ticket: TicketDetail }) {
  const { vocab } = useSession()
  const missing = ticket.missing_info.map((code) => labelOf(vocab.missing_info, code))

  return (
    <section className="panel" aria-labelledby="panel-details">
      <h3 id="panel-details">Ayrıntılar</h3>
      <p className="description">{ticket.description}</p>
      <dl className="facts">
        <dt>Konum</dt>
        <dd>{ticket.location}</dd>
        <dt>Talep sahibi</dt>
        <dd>{ticket.created_by.display_name}</dd>
        <dt>Açılış</dt>
        <dd>{formatDateTime(ticket.created_at)}</dd>
        <dt>Son güncelleme</dt>
        <dd>{formatDateTime(ticket.updated_at)}</dd>
        <dt>Ekip</dt>
        <dd>{ticket.team ? labelOf(vocab.teams, ticket.team.code) : 'Henüz yönlendirilmedi'}</dd>
        <dt>Görevli</dt>
        <dd>{ticket.assignee?.display_name ?? '—'}</dd>
        <dt>Eksik bilgi</dt>
        <dd>{missing.length > 0 ? missing.join(', ') : '—'}</dd>
      </dl>
    </section>
  )
}

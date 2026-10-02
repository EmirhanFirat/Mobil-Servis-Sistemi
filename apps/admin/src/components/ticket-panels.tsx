import { useState, type FormEvent } from 'react'

import { transitionAction } from '../lib/actions'
import type { ApiClient } from '../lib/api'
import { ApiError } from '../lib/api'
import { describeEvent, eventNote } from '../lib/events'
import { buildPatch, suggestedTeamId } from '../lib/forms'
import { formatDateTime, labelOf } from '../lib/format'
import type {
  Category,
  Priority,
  TeamWithMembers,
  TicketDetail,
  TicketStatus,
  Vocabulary,
} from '../lib/types'
import { Notice } from './ui'

interface PanelProps {
  ticket: TicketDetail
  vocab: Vocabulary
  api: ApiClient
  /** İşlem başarılı olunca (veya durum değişmiş çıkınca) ayrıntıyı yenilemek ve mesaj göstermek için. */
  onChanged: (message?: string) => Promise<void> | void
}

function failureText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

/** Sunucunun izin verdiği (allowed_transitions) durum geçişlerini düğme olarak sunar. */
export function TransitionPanel({ ticket, api, onChanged }: Omit<PanelProps, 'vocab'>) {
  const [pending, setPending] = useState<TicketStatus | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const chosen = pending ? transitionAction(ticket.status, pending) : null

  function cancel() {
    setPending(null)
    setNote('')
    setError(null)
  }

  async function confirm() {
    if (!pending || busy) return
    setBusy(true)
    setError(null)
    try {
      await api.transition(ticket.id, pending, note.trim() || undefined)
      setPending(null)
      setNote('')
      await onChanged('Durum güncellendi.')
    } catch (failure) {
      setError(failureText(failure, 'İşlem yapılamadı.'))
      if (failure instanceof ApiError && (failure.status === 409 || failure.status === 403)) {
        setPending(null)
        await onChanged() // durum başka biri tarafından değişmiş olabilir
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="panel-transition">
      <h3 id="panel-transition">Durum işlemleri</h3>
      {ticket.allowed_transitions.length === 0 ? (
        <p className="muted">Bu talepte yapılabilecek bir durum işlemi yok.</p>
      ) : chosen ? (
        <div className="stack">
          <strong>{chosen.label}</strong>
          {chosen.hint ? <p className="muted">{chosen.hint}</p> : null}
          <label className="field">
            <span>Not (isteğe bağlı)</span>
            <textarea
              value={note}
              maxLength={500}
              rows={2}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {error ? <Notice tone="error">{error}</Notice> : null}
          <div className="row">
            <button
              type="button"
              className={chosen.destructive ? 'btn btn-danger' : 'btn btn-primary'}
              onClick={confirm}
              disabled={busy}>
              {busy ? 'İşleniyor…' : 'Onayla'}
            </button>
            <button type="button" className="btn" onClick={cancel} disabled={busy}>
              Vazgeç
            </button>
          </div>
        </div>
      ) : (
        <div className="stack">
          {error ? <Notice tone="error">{error}</Notice> : null}
          <div className="row wrap">
            {ticket.allowed_transitions.map((to) => {
              const action = transitionAction(ticket.status, to)
              return (
                <button
                  key={to}
                  type="button"
                  className={action.destructive ? 'btn btn-danger' : 'btn'}
                  onClick={() => {
                    setError(null)
                    setPending(to)
                  }}>
                  {action.label}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}

/** Ekip (ve isteğe bağlı görevli) ataması. Ekip, kategorisinin varsayılan ekibinden önerilir. */
export function AssignPanel({
  ticket,
  teams,
  vocab,
  api,
  onChanged,
}: PanelProps & { teams: TeamWithMembers[] }) {
  const [teamId, setTeamId] = useState(() => suggestedTeamId(ticket, teams, vocab))
  const [assigneeId, setAssigneeId] = useState(ticket.assignee?.id ?? '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const team = teams.find((item) => item.id === teamId)
  const members = team?.members ?? []
  const defaultTeamCode = ticket.category ? vocab.category_default_team[ticket.category] : null
  const defaultTeam = teams.find((item) => item.code === defaultTeamCode)
  const disabled = !ticket.can_assign

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (disabled || !teamId || busy) return
    setBusy(true)
    setError(null)
    try {
      await api.assign(ticket.id, {
        team_id: teamId,
        assignee_id: assigneeId || null,
        note: note.trim() || undefined,
      })
      await onChanged('Atama kaydedildi.')
    } catch (failure) {
      setError(failureText(failure, 'Atama yapılamadı.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="panel-assign">
      <h3 id="panel-assign">Ekip ve görevli ataması</h3>
      {disabled ? (
        <p className="muted">Çözülmüş veya kapatılmış talep yeniden atanamaz.</p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span>Ekip</span>
            <select
              aria-label="Ekip"
              value={teamId}
              onChange={(event) => {
                setTeamId(event.target.value)
                setAssigneeId('') // görevli seçilen ekibin üyesi olmalı
              }}>
              <option value="">Ekip seç…</option>
              {teams.map((item) => (
                <option key={item.id} value={item.id}>
                  {labelOf(vocab.teams, item.code) || item.name}
                </option>
              ))}
            </select>
          </label>
          {defaultTeam && defaultTeam.id !== teamId ? (
            <p className="muted">
              Kategoriye göre önerilen ekip:{' '}
              <button type="button" className="link" onClick={() => setTeamId(defaultTeam.id)}>
                {labelOf(vocab.teams, defaultTeam.code)}
              </button>
            </p>
          ) : null}
          <label className="field">
            <span>Görevli</span>
            <select
              aria-label="Görevli"
              value={assigneeId}
              disabled={!teamId}
              onChange={(event) => setAssigneeId(event.target.value)}>
              <option value="">Görevli seçme (ekip kuyruğuna bırak)</option>
              {members.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.display_name}
                </option>
              ))}
            </select>
          </label>
          {teamId && members.length === 0 ? (
            <p className="muted">Bu ekipte henüz görevli yok. Ekipler sayfasından ekleyebilirsin.</p>
          ) : null}
          <label className="field">
            <span>Not (isteğe bağlı)</span>
            <textarea
              value={note}
              maxLength={500}
              rows={2}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {error ? <Notice tone="error">{error}</Notice> : null}
          <div className="row">
            <button type="submit" className="btn btn-primary" disabled={!teamId || busy}>
              {busy ? 'Kaydediliyor…' : ticket.team ? 'Yeniden ata' : 'Ata'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

/** Öncelik, kategori ve eksik bilgi düzeltmesi. Yalnızca değişen alanlar gönderilir. */
export function CorrectionPanel({ ticket, vocab, api, onChanged }: PanelProps) {
  const [priority, setPriority] = useState<Priority>(ticket.priority)
  const [category, setCategory] = useState<Category | ''>(ticket.category ?? '')
  const [missing, setMissing] = useState<string[]>(ticket.missing_info)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patch = buildPatch(ticket, { priority, category, missing, note })
  const disabled = !ticket.can_edit

  function toggleMissing(code: string, checked: boolean) {
    setMissing((current) =>
      checked ? [...current, code] : current.filter((item) => item !== code),
    )
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (disabled || !patch || busy) return
    setBusy(true)
    setError(null)
    try {
      await api.patchTicket(ticket.id, patch)
      await onChanged('Düzeltme kaydedildi.')
    } catch (failure) {
      setError(failureText(failure, 'Düzeltme kaydedilemedi.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="panel-correction">
      <h3 id="panel-correction">Düzeltme</h3>
      {disabled ? (
        <p className="muted">Kapatılmış talep düzeltilemez.</p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span>Öncelik</span>
            <select
              aria-label="Öncelik"
              value={priority}
              onChange={(event) => setPriority(event.target.value as Priority)}>
              {vocab.priorities.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Kategori</span>
            <select
              aria-label="Kategori"
              value={category}
              onChange={(event) => setCategory(event.target.value as Category | '')}>
              <option value="">Belirtilmemiş</option>
              {vocab.categories.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="field">
            <legend>Eksik bilgi</legend>
            {vocab.missing_info.map((item) => (
              <label key={item.code} className="check">
                <input
                  type="checkbox"
                  checked={missing.includes(item.code)}
                  onChange={(event) => toggleMissing(item.code, event.target.checked)}
                />
                {item.label}
              </label>
            ))}
          </fieldset>
          <label className="field">
            <span>Düzeltme notu (isteğe bağlı)</span>
            <textarea
              value={note}
              maxLength={500}
              rows={2}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {error ? <Notice tone="error">{error}</Notice> : null}
          <div className="row">
            <button type="submit" className="btn btn-primary" disabled={!patch || busy}>
              {busy ? 'Kaydediliyor…' : 'Düzeltmeyi kaydet'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

/** Olay geçmişi: kim, ne zaman, neyi değiştirdi (en yeni üstte). */
export function History({ ticket, vocab }: { ticket: TicketDetail; vocab: Vocabulary }) {
  const events = [...ticket.events].reverse()
  return (
    <section className="panel" aria-labelledby="panel-history">
      <h3 id="panel-history">Geçmiş</h3>
      <ol className="timeline">
        {events.map((event) => {
          const note = eventNote(event)
          return (
            <li key={event.id}>
              <p>{describeEvent(event, vocab)}</p>
              {note ? <p className="note">“{note}”</p> : null}
              <time className="muted" dateTime={event.created_at}>
                {formatDateTime(event.created_at)}
              </time>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

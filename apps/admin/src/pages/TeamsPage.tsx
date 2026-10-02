import { useCallback, useState } from 'react'

import { ErrorBox, Loading, Notice } from '../components/ui'
import type { ApiClient } from '../lib/api'
import { useSession } from '../lib/auth-context'
import { labelOf } from '../lib/format'
import type { TeamWithMembers, User, Vocabulary } from '../lib/types'
import { useResource } from '../lib/use-resource'

export default function TeamsPage() {
  const { api, vocab } = useSession()
  const loadTeams = useCallback(() => api.listTeams(), [api])
  const loadUsers = useCallback(() => api.listUsers(), [api])
  const teams = useResource(loadTeams)
  const users = useResource(loadUsers)
  const [flash, setFlash] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  if ((teams.loading && !teams.data) || (users.loading && !users.data)) {
    return <Loading message="Ekipler yükleniyor…" />
  }
  const failure = (teams.error && !teams.data ? teams.error : null) ?? (users.error && !users.data ? users.error : null)
  if (failure || !teams.data || !users.data) {
    return (
      <ErrorBox
        error={failure ?? new Error('Ekipler yüklenemedi.')}
        onRetry={() => {
          void teams.retry()
          void users.retry()
        }}
      />
    )
  }

  // Daralmış değerler: kapanışlar (map/filter) içinde `teams.data` yeniden null olabilir sayılır.
  const teamList = teams.data
  const technicians = users.data.filter((person) => person.role === 'technician' && person.is_active)

  async function refresh(text: string) {
    await Promise.all([teams.reload(), users.reload()])
    setFlash({ tone: 'success', text })
  }

  return (
    <>
      <div className="page-head">
        <h1>Ekipler</h1>
        <p className="muted">
          Teknik görevliler yalnızca üyesi oldukları ekibin taleplerini görür ve işler.
        </p>
      </div>
      {flash ? <Notice tone={flash.tone}>{flash.text}</Notice> : null}
      <div className="cards">
        {teamList.map((team) => (
          <TeamCard
            key={team.id}
            team={team}
            technicians={technicians}
            vocab={vocab}
            api={api}
            onChanged={refresh}
            onError={(text) => setFlash({ tone: 'error', text })}
          />
        ))}
      </div>
    </>
  )
}

interface TeamCardProps {
  team: TeamWithMembers
  technicians: User[]
  vocab: Vocabulary
  api: ApiClient
  onChanged: (message: string) => Promise<void>
  onError: (message: string) => void
}

function TeamCard({ team, technicians, vocab, api, onChanged, onError }: TeamCardProps) {
  const [selected, setSelected] = useState('')
  const memberIds = new Set(team.members.map((member) => member.id))
  const candidates = technicians.filter((person) => !memberIds.has(person.id))
  const name = labelOf(vocab.teams, team.code) || team.name

  async function add() {
    if (!selected) return
    try {
      await api.addMember(team.id, selected)
      setSelected('')
      await onChanged('Görevli ekibe eklendi.')
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : 'Eklenemedi.')
    }
  }

  async function remove(userId: string) {
    try {
      await api.removeMember(team.id, userId)
      await onChanged('Görevli ekipten çıkarıldı.')
    } catch (failure) {
      // Açık işi olan görevli çıkarılamaz; sunucunun Türkçe mesajı gösterilir.
      onError(failure instanceof Error ? failure.message : 'Çıkarılamadı.')
    }
  }

  return (
    <section className="panel" aria-label={name}>
      <h3>{name}</h3>
      {team.members.length === 0 ? (
        <p className="muted">Henüz görevli yok.</p>
      ) : (
        <ul className="members">
          {team.members.map((member) => (
            <li key={member.id}>
              <span>{member.display_name}</span>
              <button
                type="button"
                className="btn btn-small"
                aria-label={`${member.display_name} görevlisini ${name} ekibinden çıkar`}
                onClick={() => void remove(member.id)}>
                Çıkar
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="row">
        <select
          aria-label={`${name} ekibine eklenecek görevli`}
          value={selected}
          onChange={(event) => setSelected(event.target.value)}>
          <option value="">Görevli ekle…</option>
          {candidates.map((person) => (
            <option key={person.id} value={person.id}>
              {person.display_name}
            </option>
          ))}
        </select>
        <button type="button" className="btn" disabled={!selected} onClick={() => void add()}>
          Ekle
        </button>
      </div>
    </section>
  )
}

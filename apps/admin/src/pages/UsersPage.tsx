import { useCallback, useState, type FormEvent } from 'react'

import { Badge, ErrorBox, Loading, Notice } from '../components/ui'
import { useSession } from '../lib/auth-context'
import { validateUserForm } from '../lib/forms'
import { labelOf } from '../lib/format'
import type { Role, User } from '../lib/types'
import { useResource } from '../lib/use-resource'

export default function UsersPage() {
  const { api, vocab, user: me } = useSession()
  const load = useCallback(() => api.listUsers(), [api])
  const { data, error, loading, retry, reload } = useResource(load)
  const [flash, setFlash] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  async function update(user: User, body: { role?: Role; is_active?: boolean }, success: string) {
    setFlash(null)
    try {
      await api.patchUser(user.id, body)
      await reload()
      setFlash({ tone: 'success', text: success })
    } catch (failure) {
      setFlash({
        tone: 'error',
        text: failure instanceof Error ? failure.message : 'Güncellenemedi.',
      })
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Kullanıcılar</h1>
      </div>
      {flash ? <Notice tone={flash.tone}>{flash.text}</Notice> : null}

      <NewUserForm
        onCreated={async (name) => {
          await reload()
          setFlash({ tone: 'success', text: `${name} oluşturuldu.` })
        }}
      />

      {loading && !data ? (
        <Loading message="Kullanıcılar yükleniyor…" />
      ) : error && !data ? (
        <ErrorBox error={error} onRetry={retry} />
      ) : data ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ad</th>
                <th>Kullanıcı adı</th>
                <th>Rol</th>
                <th>Ekipler</th>
                <th>Durum</th>
              </tr>
            </thead>
            <tbody>
              {data.map((person) => {
                const self = person.id === me.id
                return (
                  <tr key={person.id}>
                    <td>{person.display_name}</td>
                    <td>{person.username}</td>
                    <td>
                      <select
                        aria-label={`${person.display_name} rolü`}
                        value={person.role}
                        disabled={self}
                        onChange={(event) =>
                          void update(person, { role: event.target.value as Role }, 'Rol güncellendi.')
                        }>
                        {vocab.roles.map((role) => (
                          <option key={role.code} value={role.code}>
                            {role.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {person.teams.length > 0
                        ? person.teams.map((team) => labelOf(vocab.teams, team.code)).join(', ')
                        : '—'}
                    </td>
                    <td className="nowrap">
                      <Badge kind={person.is_active ? 'resolved' : 'closed'}>
                        {person.is_active ? 'Aktif' : 'Pasif'}
                      </Badge>{' '}
                      <button
                        type="button"
                        className="btn btn-small"
                        disabled={self}
                        title={self ? 'Kendi hesabını devre dışı bırakamazsın.' : undefined}
                        onClick={() =>
                          void update(
                            person,
                            { is_active: !person.is_active },
                            person.is_active ? 'Hesap devre dışı bırakıldı.' : 'Hesap etkinleştirildi.',
                          )
                        }>
                        {person.is_active ? 'Devre dışı bırak' : 'Etkinleştir'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  )
}

function NewUserForm({ onCreated }: { onCreated: (displayName: string) => Promise<void> }) {
  const { api, vocab } = useSession()
  const [form, setForm] = useState({ username: '', display_name: '', password: '' })
  const [role, setRole] = useState<Role>('requester')
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const errors = validateUserForm(form)
  const shown = (field: keyof typeof form) => (submitted ? errors[field] : undefined)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setSubmitted(true)
    if (Object.keys(errors).length > 0) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.createUser({
        username: form.username.trim(),
        display_name: form.display_name.trim(),
        password: form.password,
        role,
      })
      setForm({ username: '', display_name: '', password: '' })
      setRole('requester')
      setSubmitted(false)
      await onCreated(created.display_name)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Kullanıcı oluşturulamadı.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <details className="panel">
      <summary>Yeni kullanıcı oluştur</summary>
      <form className="grid-form" onSubmit={submit} noValidate>
        <label className="field">
          <span>Kullanıcı adı</span>
          <input
            value={form.username}
            autoComplete="off"
            onChange={(event) => setForm({ ...form, username: event.target.value })}
          />
          {shown('username') ? <small className="error-text">{shown('username')}</small> : null}
        </label>
        <label className="field">
          <span>Görünen ad</span>
          <input
            value={form.display_name}
            onChange={(event) => setForm({ ...form, display_name: event.target.value })}
          />
          {shown('display_name') ? <small className="error-text">{shown('display_name')}</small> : null}
        </label>
        <label className="field">
          <span>Geçici parola</span>
          <input
            type="password"
            value={form.password}
            autoComplete="new-password"
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
          {shown('password') ? <small className="error-text">{shown('password')}</small> : null}
        </label>
        <label className="field">
          <span>Rol</span>
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            {vocab.roles.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <div className="row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Oluşturuluyor…' : 'Oluştur'}
          </button>
        </div>
      </form>
    </details>
  )
}

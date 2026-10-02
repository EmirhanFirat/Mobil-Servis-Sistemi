import { useState, type FormEvent } from 'react'

import { Notice } from '../components/ui'
import { useAuth } from '../lib/auth-context'
import { API_URL } from '../lib/config'

export default function LoginPage() {
  const { signIn, notice } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    if (!username.trim() || !password) {
      setError('Kullanıcı adı ve parolayı gir.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await signIn(username.trim(), password)
      // Başarılı girişte yönlendirme kendiliğinden ana sayfaya geçer.
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Giriş yapılamadı.')
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <form className="card stack" onSubmit={submit}>
        <div>
          <h1>TalepAkış Yönetim</h1>
          <p className="muted">Yönetici girişi</p>
        </div>
        {notice ? <Notice>{notice}</Notice> : null}
        <label className="field">
          <span>Kullanıcı adı</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            autoFocus
          />
        </label>
        <label className="field">
          <span>Parola</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
        </button>
        <p className="muted small">Sunucu: {API_URL}</p>
      </form>
    </main>
  )
}

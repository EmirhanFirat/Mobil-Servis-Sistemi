import { NavLink, Outlet } from 'react-router'

import { useSession } from '../lib/auth-context'

export default function Layout() {
  const { user, signOut } = useSession()

  return (
    <div className="shell">
      <header className="topbar">
        <strong className="brand">TalepAkış Yönetim</strong>
        <nav aria-label="Ana gezinme">
          <NavLink to="/" end>
            Talepler
          </NavLink>
          <NavLink to="/kullanicilar">Kullanıcılar</NavLink>
          <NavLink to="/ekipler">Ekipler</NavLink>
          <NavLink to="/model-karsilastirma">Model karşılaştırma</NavLink>
        </nav>
        <div className="spacer" />
        <span className="muted">{user.display_name}</span>
        <button type="button" className="btn" onClick={signOut}>
          Çıkış yap
        </button>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

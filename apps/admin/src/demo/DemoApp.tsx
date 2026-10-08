import { useCallback, useMemo } from 'react'
import { HashRouter, NavLink, Navigate, Outlet, Route, Routes } from 'react-router'

import { API_URL } from '../lib/config'
import { createDemoClient, readDemoToken, storeDemoToken } from '../lib/demo-api'
import { loadStaticBundle } from '../lib/static-experiments'
import { useResource } from '../lib/use-resource'
import DemoPage from './DemoPage'
import ResultsPage from './ResultsPage'

const REPO_URL = 'https://github.com/EmirhanFirat/Mobil-Servis-Sistemi'

function DemoLayout() {
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">TalepAkış · canlı demo</span>
        <nav>
          <NavLink to="/" end>
            Jev ile dene
          </NavLink>
          <NavLink to="/sonuclar">Ölçüm sonuçları</NavLink>
        </nav>
        <div className="spacer" />
        <a className="muted small" href={REPO_URL} target="_blank" rel="noreferrer noopener">
          Kaynak kod
        </a>
      </header>
      <main className="content">
        <Outlet />
        <footer className="muted small demo-footer">
          Portföy demosu · ücretsiz barındırma (Render + Neon) · sunucu boştayken uyur · yazdığın metin Jev API
          sağlayıcısına gönderilir ve süre sonunda silinir.
        </footer>
      </main>
    </div>
  )
}

export default function DemoApp() {
  const client = useMemo(
    () =>
      createDemoClient({
        baseUrl: API_URL,
        getToken: readDemoToken,
        onUnauthorized: () => storeDemoToken(null),
      }),
    [],
  )
  // Önceden hazırlanmış sonuçlar ve sözlük: API'den bağımsız (statik dosya).
  const load = useCallback(() => loadStaticBundle(import.meta.env.BASE_URL), [])
  const { data: bundle, error, loading, retry } = useResource(load)

  return (
    <HashRouter>
      <Routes>
        <Route element={<DemoLayout />}>
          <Route index element={<DemoPage client={client} vocab={bundle?.vocabulary ?? null} />} />
          <Route
            path="sonuclar"
            element={<ResultsPage bundle={bundle} error={error} loading={loading} onRetry={retry} />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

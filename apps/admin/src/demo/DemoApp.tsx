import { useCallback, useEffect, useMemo } from 'react'
import { HashRouter, NavLink, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'

import { API_URL } from '../lib/config'
import { createDemoClient, readDemoToken, storeDemoToken } from '../lib/demo-api'
import { loadStaticBundle } from '../lib/static-experiments'
import { useResource } from '../lib/use-resource'
import AboutPage from './AboutPage'
import DemoPage from './DemoPage'
import ResultsPage from './ResultsPage'

const REPO_URL = 'https://github.com/EmirhanFirat/Mobil-Servis-Sistemi'

/** GitHub işareti (satır içi SVG: CSP dış kaynak kabul etmez). */
function GithubIcon() {
  return (
    <svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
      />
    </svg>
  )
}

/** HashRouter sayfa değişiminde kaydırma konumunu korur; yeni sayfa en üstten açılsın. */
function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

function DemoLayout() {
  return (
    <div className="shell">
      <ScrollToTop />
      <header className="topbar demo-topbar">
        <span className="brand">
          TalepAkış<span className="brand-sub"> · Kampüs Destek</span>
        </span>
        <nav aria-label="Demo sayfaları">
          <NavLink to="/" end>
            Talep oluştur
          </NavLink>
          <NavLink to="/hakkinda">Hakkında</NavLink>
          <NavLink to="/sonuclar">Sonuçlar</NavLink>
        </nav>
        <div className="spacer" />
        <a
          className="repo-link"
          href={REPO_URL}
          target="_blank"
          rel="noreferrer noopener"
          aria-label="Kaynak kod (GitHub)"
          title="Kaynak kod (GitHub)"
        >
          <GithubIcon />
          <span className="repo-text">Kaynak kod</span>
        </a>
      </header>
      <main className="content">
        <Outlet />
        <footer className="muted small demo-footer">
          Portföy demosu · Render + Neon üzerinde ücretsiz barındırılır.
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
            path="hakkinda"
            element={<AboutPage vocab={bundle?.vocabulary ?? null} experiments={bundle?.source ?? null} />}
          />
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

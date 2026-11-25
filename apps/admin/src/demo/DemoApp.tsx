import { useCallback, useEffect, useMemo, useState } from 'react'
import { HashRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'

import { API_URL } from '../lib/config'
import { createDemoClient, readDemoToken, storeDemoToken } from '../lib/demo-api'
import { loadStaticBundle } from '../lib/static-experiments'
import { useResource } from '../lib/use-resource'
import AboutPage from './AboutPage'
import DemoPage from './DemoPage'
import LandingPage, { REQUEST_PATH } from './LandingPage'
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

/** Marka işareti: akış oku taşıyan anahtar biçimli rozet (satır içi SVG). */
function BrandMark() {
  return (
    <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="var(--lp-accent)" />
      <path
        d="M8 11h9m-3-3 3 3-3 3M24 21h-9m3-3-3 3 3 3"
        fill="none"
        stroke="var(--lp-navy)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
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

const NAV = [
  { to: '/', label: 'Tanıtım', end: true },
  { to: REQUEST_PATH, label: 'Talep oluştur', end: false },
  { to: '/hakkinda', label: 'Hakkında', end: false },
  { to: '/sonuclar', label: 'Sonuçlar', end: false },
]

function SiteHeader() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  // Sayfa değişince mobil menü kapanır (render sırasında, önceki yola göre).
  const [seenPath, setSeenPath] = useState(pathname)
  if (seenPath !== pathname) {
    setSeenPath(pathname)
    setOpen(false)
  }

  return (
    <header className="site-header">
      <div className="utility-bar">
        <div className="site-container utility-inner">
          <span>
            Portföy demosu<span className="utility-long"> · talepler gerçek bir bakım ekibine iletilmez</span>
          </span>
          <span className="utility-right">
            Acil durum: <strong>112</strong>
          </span>
        </div>
      </div>
      <div className="navbar">
        <div className="site-container navbar-inner">
          <Link to="/" className="site-brand" aria-label="TalepAkış ana sayfa">
            <BrandMark />
            <span>
              TalepAkış<span className="site-brand-sub">Kampüs Destek</span>
            </span>
          </Link>
          <nav id="site-nav" className={`site-nav${open ? ' open' : ''}`} aria-label="Demo sayfaları">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end}>
                {item.label}
              </NavLink>
            ))}
            <a className="site-nav-repo" href={REPO_URL} target="_blank" rel="noreferrer noopener">
              Kaynak kod (GitHub)
            </a>
          </nav>
          <div className="navbar-actions">
            <a
              className="repo-link"
              href={REPO_URL}
              target="_blank"
              rel="noreferrer noopener"
              aria-label="Kaynak kod (GitHub)"
              title="Kaynak kod (GitHub)"
            >
              <GithubIcon />
            </a>
            {pathname !== REQUEST_PATH ? (
              <Link className="lp-btn lp-btn-accent nav-cta" to={REQUEST_PATH}>
                Talep bildir
              </Link>
            ) : null}
            <button
              type="button"
              className="menu-toggle"
              aria-expanded={open}
              aria-controls="site-nav"
              aria-label={open ? 'Menüyü kapat' : 'Menüyü aç'}
              onClick={() => setOpen(!open)}
            >
              <span aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-container footer-grid">
        <div className="footer-about">
          <span className="site-brand">
            <BrandMark />
            <span>TalepAkış</span>
          </span>
          <p>
            Kampüs ve yurt bakım ekipleri için Türkçe servis talebi yönlendirme. Bir araştırma ve portföy projesidir.
          </p>
        </div>
        <div>
          <h2>Portal</h2>
          <ul>
            <li>
              <Link to={REQUEST_PATH}>Talep oluştur</Link>
            </li>
            <li>
              <Link to="/hakkinda">Hakkında</Link>
            </li>
            <li>
              <Link to="/sonuclar">Ölçüm sonuçları</Link>
            </li>
          </ul>
        </div>
        <div>
          <h2>Proje</h2>
          <ul>
            <li>
              <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
                Kaynak kod (GitHub)
              </a>
            </li>
            <li>Mobil uygulama: React Native</li>
            <li>API: FastAPI + PostgreSQL</li>
          </ul>
        </div>
        <div>
          <h2>Bilmen gerekenler</h2>
          <ul>
            <li>Talepler gerçek bir ekibe iletilmez.</li>
            <li>Demo talepleri 72 saat sonra silinir.</li>
            <li>
              Acil durumda <strong>112</strong>&apos;yi ara.
            </li>
          </ul>
        </div>
      </div>
      <div className="site-container footer-bottom">Portföy demosu · Render + Neon üzerinde ücretsiz barındırılır.</div>
    </footer>
  )
}

function DemoLayout() {
  const { pathname } = useLocation()
  const fullBleed = pathname === '/'
  return (
    <div className="shell demo-shell">
      <ScrollToTop />
      <SiteHeader />
      <main className={fullBleed ? 'landing-main' : 'content'}>
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  )
}

/** Tanıtımdaki hızlı başlangıç kutusundan gelen başlık forma aktarılır. */
function RequestRoute(props: Omit<Parameters<typeof DemoPage>[0], 'initialTitle'>) {
  const { state } = useLocation()
  const title = typeof state?.title === 'string' ? state.title : ''
  return <DemoPage {...props} initialTitle={title} />
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
          <Route index element={<LandingPage client={client} />} />
          <Route path="talep" element={<RequestRoute client={client} vocab={bundle?.vocabulary ?? null} />} />
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

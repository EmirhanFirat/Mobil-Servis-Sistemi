import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import Layout from './components/Layout'
import { ErrorBox, Loading } from './components/ui'
import { AuthProvider } from './lib/auth'
import { useAuth } from './lib/auth-context'
import LoginPage from './pages/LoginPage'
import ModelComparisonPage from './pages/ModelComparisonPage'
import TeamsPage from './pages/TeamsPage'
import TicketPage from './pages/TicketPage'
import TicketsPage from './pages/TicketsPage'
import UsersPage from './pages/UsersPage'

function AppRoutes() {
  const { status, error, retry } = useAuth()

  if (status === 'loading') return <Loading message="Oturum kontrol ediliyor…" />
  if (status === 'error') {
    return <ErrorBox error={error ?? new Error('Sunucuya ulaşılamadı.')} onRetry={retry} />
  }

  // Yönlendirme yalnızca kolaylıktır; erişimi asıl sunucu denetler (her istekte token ve rol).
  if (status === 'signedOut') {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<TicketsPage />} />
        <Route path="talepler/:id" element={<TicketPage />} />
        <Route path="kullanicilar" element={<UsersPage />} />
        <Route path="ekipler" element={<TeamsPage />} />
        <Route path="model-karsilastirma" element={<ModelComparisonPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

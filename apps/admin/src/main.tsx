import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const root = createRoot(document.getElementById('root')!)

// Derleme kipi: `VITE_APP_MODE=demo` herkese açık demoyu (yönetici ekranları OLMADAN), aksi hâlde
// yönetici panelini üretir. Dinamik içe aktarma, kullanılmayan kipin kodunun pakete girmemesini sağlar.
if (import.meta.env.VITE_APP_MODE === 'demo') {
  void import('./demo/DemoApp').then(({ default: DemoApp }) =>
    root.render(
      <StrictMode>
        <DemoApp />
      </StrictMode>,
    ),
  )
} else {
  void import('./App.tsx').then(({ default: App }) =>
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    ),
  )
}

import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

import { demoCspPlugin } from './csp.ts'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const demo = env.VITE_APP_MODE === 'demo'
  return {
    // Herkese açık demo derlemesinde (VITE_APP_MODE=demo) CSP sayfaya gömülür.
    plugins: [react(), ...(demo ? [demoCspPlugin(env.VITE_API_URL)] : [])],
    // API'nin CORS izin listesi bu adresi içerir (TALEPAKIS_CORS_ORIGINS).
    server: { port: 5173, strictPort: true },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test-setup.ts'],
    },
  }
})

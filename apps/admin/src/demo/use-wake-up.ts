import { useCallback, useEffect, useState } from 'react'

import type { DemoClient } from '../lib/demo-api'
import type { DemoStatus } from '../lib/demo-types'

/**
 * Ücretsiz barındırmada API (ve veritabanı) boştayken uyur; ilk ziyarette uyanması yaklaşık bir
 * dakika sürebilir. Sayfa açılınca model çağrısı YAPMAYAN tek bir hazırlık isteği gönderilir.
 *
 * Sınırlı yeniden deneme: en çok `WAKE_ATTEMPTS` deneme, aralarında kısa bekleme; sonra durur ve
 * kullanıcıya "Yeniden dene" düğmesi verir. Sınırsız yoklama veya arka planda sürekli istek YOK.
 */
export const WAKE_ATTEMPTS = 3
export const WAKE_PAUSE_MS = 8_000

export type WakeState =
  | { phase: 'checking'; attempt: number }
  /** Önceki deneme sonuçsuz kaldı (sunucu/veritabanı uyanıyor); kısa beklemeden sonra yeniden denenecek. */
  | { phase: 'waiting'; attempt: number }
  | { phase: 'ready'; status: DemoStatus; wakeMs: number; attempts: number }
  /** Denemeler tükendi: kullanıcı kontrollü yeniden deneme. */
  | { phase: 'failed'; error: Error; attempts: number }

export function useWakeUp(client: DemoClient, now: () => number = () => performance.now()) {
  const [state, setState] = useState<WakeState>({ phase: 'checking', attempt: 1 })
  const [run, setRun] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const started = now()

    const pause = (ms: number) =>
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, ms)
      })

    void (async () => {
      let lastError: Error = new Error('Sunucuya ulaşılamadı.')
      for (let attempt = 1; attempt <= WAKE_ATTEMPTS; attempt++) {
        if (cancelled) return
        setState({ phase: 'checking', attempt })
        try {
          const status = await client.status()
          if (cancelled) return
          if (status.database_ready) {
            setState({ phase: 'ready', status, wakeMs: now() - started, attempts: attempt })
            return
          }
          lastError = new Error('Veritabanı uyanıyor.')
        } catch (error) {
          lastError = error instanceof Error ? error : new Error(String(error))
        }
        if (attempt < WAKE_ATTEMPTS) {
          if (cancelled) return
          setState({ phase: 'waiting', attempt })
          await pause(WAKE_PAUSE_MS)
        }
      }
      if (!cancelled) setState({ phase: 'failed', error: lastError, attempts: WAKE_ATTEMPTS })
    })()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
    // `now` (test için) ve `client` sabit kabul edilir; `run` yeniden denemeyi başlatır.
  }, [client, run]) // eslint-disable-line react-hooks/exhaustive-deps

  const retry = useCallback(() => setRun((value) => value + 1), [])
  return { state, retry }
}

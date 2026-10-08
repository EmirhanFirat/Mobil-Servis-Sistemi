import { useCallback, useRef, useState } from 'react'

import { ApiError, NetworkError } from '../lib/api'
import { readDemoToken, storeDemoToken, type DemoClient } from '../lib/demo-api'
import type { DemoDecisionInput, DemoDecisionResult, DemoDecisionSummary } from '../lib/demo-types'

/** Bir istek sonucu ve bu isteğin uçtan uca bekleme süresi (istemci ölçümü; model süresi DEĞİL). */
export interface DecisionRun {
  result: DemoDecisionResult
  /** Düğmeye basıştan yanıtın gelişine kadar geçen süre (ms). */
  e2eMs: number | null
}

export const CONNECTION_LOST_HELP =
  'Bağlantı koptu veya yanıt zamanında gelmedi. İstek sunucuda kaydedilmiş ve çalışmış olabilir: ' +
  '"Önceki denemelerim" listesine bak. Aynı metni yeniden göndermek güvenlidir; aynı metin ikinci ' +
  'bir Jev çağrısı açmaz.'

async function ensureSession(client: DemoClient): Promise<void> {
  if (readDemoToken()) return
  const session = await client.openSession()
  storeDemoToken(session.access_token)
}

/**
 * Karar gönderme akışı. Çift tıklama ve eşzamanlı gönderim istemcide engellenir (tek uçuşta istek);
 * asıl koruma sunucudadır (aynı metin ikinci çağrı açmaz). Yenileme/yeniden gönderme yeni ücretli
 * çağrı başlatmaz.
 */
export function useDemoDecision(client: DemoClient, now: () => number = () => performance.now()) {
  const [busy, setBusy] = useState(false)
  const [run, setRun] = useState<DecisionRun | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [history, setHistory] = useState<DemoDecisionSummary[]>([])
  const inFlight = useRef(false)

  const refreshHistory = useCallback(async () => {
    if (!readDemoToken()) return
    try {
      setHistory(await client.listDecisions())
    } catch {
      // Geçmiş listesi yardımcı bilgidir; hata ana akışı bozmaz.
    }
  }, [client])

  const guarded = useCallback(
    async (work: () => Promise<DecisionRun | null>) => {
      if (inFlight.current) return // çift tıklama: ikinci istek gönderilmez
      inFlight.current = true
      setBusy(true)
      setError(null)
      try {
        const next = await work()
        if (next) setRun(next)
        await refreshHistory()
      } catch (failure) {
        const error = failure instanceof Error ? failure : new Error(String(failure))
        setError(error instanceof NetworkError ? new NetworkError(CONNECTION_LOST_HELP, error.timedOut) : error)
        await refreshHistory()
      } finally {
        inFlight.current = false
        setBusy(false)
      }
    },
    [refreshHistory],
  )

  const submit = useCallback(
    (input: DemoDecisionInput) =>
      guarded(async () => {
        const started = now()
        await ensureSession(client)
        let result: DemoDecisionResult
        try {
          result = await client.decide(input)
        } catch (failure) {
          // 401: oturum süresi dolmuş/geçersiz. İstek işlenmeden reddedilir (ücretli çağrı yok);
          // yeni oturumla BİR kez yeniden denenir.
          if (failure instanceof ApiError && failure.status === 401) {
            storeDemoToken(null)
            await ensureSession(client)
            result = await client.decide(input)
          } else {
            throw failure
          }
        }
        return { result, e2eMs: now() - started }
      }),
    [client, guarded, now],
  )

  /** Yalnızca OKUR; model çağrısı başlatmaz (bekleyen/çalışan talebin durumunu sorgular). */
  const check = useCallback(
    (ticketId: string) =>
      guarded(async () => {
        const result = await client.getDecision(ticketId)
        // Okuma, bir karar isteği değildir: o talebin uçtan uca bekleme süresi burada bilinmez.
        return { result, e2eMs: null }
      }),
    [client, guarded],
  )

  return { busy, run, error, history, submit, check, refreshHistory }
}

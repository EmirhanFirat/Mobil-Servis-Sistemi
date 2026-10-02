import { useCallback, useEffect, useState } from 'react'

interface Slot<T> {
  /** Bu verinin hangi `load` ile yüklendiği; `load` değişince eski veri geçersiz sayılır. */
  source: () => Promise<T>
  data: T | null
  error: Error | null
}

type Outcome<T> = { data: T } | { error: Error }

async function attempt<T>(load: () => Promise<T>): Promise<Outcome<T>> {
  try {
    return { data: await load() }
  } catch (failure) {
    return { error: failure instanceof Error ? failure : new Error(String(failure)) }
  }
}

/**
 * Bir sayfanın verisini yükler. `load` çağıranda `useCallback` ile sabitlenmelidir; kimliği
 * değişince (ör. süzgeç/sayfa) veri baştan yüklenir.
 *
 * - loading: bu `load` için henüz ne veri ne hata var (spinner)
 * - error + data: yenileme başarısız ama eski veri hâlâ gösterilebilir
 * - reload(): bir işlemden sonra spinner göstermeden yenile; retry(): spinner ile baştan dene
 */
export function useResource<T>(load: () => Promise<T>) {
  const [slot, setSlot] = useState<Slot<T>>({ source: load, data: null, error: null })

  const apply = useCallback(
    (source: () => Promise<T>, outcome: Outcome<T>) =>
      setSlot((previous) =>
        'data' in outcome
          ? { source, data: outcome.data, error: null }
          : {
              source,
              data: previous.source === source ? previous.data : null,
              error: outcome.error,
            },
      ),
    [],
  )

  useEffect(() => {
    let ignore = false
    void attempt(load).then((outcome) => {
      if (!ignore) apply(load, outcome) // sayfa kapandıysa/süzgeç değiştiyse eski yanıtı yok say
    })
    return () => {
      ignore = true
    }
  }, [load, apply])

  // Başka bir `load`un sonucu bu `load` için gösterilmez.
  const current = slot.source === load ? slot : null
  const data = current?.data ?? null
  const error = current?.error ?? null

  const reload = useCallback(async () => apply(load, await attempt(load)), [load, apply])
  const retry = useCallback(async () => {
    setSlot({ source: load, data: null, error: null })
    apply(load, await attempt(load))
  }, [load, apply])

  return { data, error, loading: data === null && error === null, retry, reload }
}

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fakeDemoClient, makeStatus } from '../demo-fixtures'
import { ApiError, NetworkError } from '../lib/api'
import { WAKE_ATTEMPTS, WAKE_PAUSE_MS, useWakeUp } from './use-wake-up'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('useWakeUp', () => {
  it('sunucu hazırsa tek istekle hazır olur ve uyanma süresi ölçülür', async () => {
    let clock = 1000
    const client = fakeDemoClient({
      status: vi.fn(async () => {
        clock += 4200 // ilk istek 4,2 sn sürdü (ücretsiz sunucu uyanıyordu)
        return makeStatus({ database_ms: 900 })
      }),
    })

    const { result } = renderHook(() => useWakeUp(client, () => clock))
    await flush()

    expect(result.current.state).toMatchObject({ phase: 'ready', wakeMs: 4200, attempts: 1 })
    expect(client.status).toHaveBeenCalledTimes(1)
  })

  it('uyanana kadar sınırlı sayıda yeniden dener ve sonra hazır olur', async () => {
    const status = vi
      .fn()
      .mockRejectedValueOnce(new NetworkError('uyuyor', true))
      .mockResolvedValueOnce(makeStatus({ database_ready: false })) // API uyandı, veritabanı henüz değil
      .mockResolvedValueOnce(makeStatus())
    const client = fakeDemoClient({ status })

    const { result } = renderHook(() => useWakeUp(client))
    await flush()
    expect(result.current.state).toEqual({ phase: 'waiting', attempt: 1 })
    await flush(WAKE_PAUSE_MS)
    expect(result.current.state).toEqual({ phase: 'waiting', attempt: 2 })
    await flush(WAKE_PAUSE_MS)

    expect(result.current.state).toMatchObject({ phase: 'ready', attempts: 3 })
    expect(status).toHaveBeenCalledTimes(3)
  })

  it('Render uyanırken dönen 502/503 hataları da sınırlı denemeye sayılır', async () => {
    const status = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(502, null, 'Sunucuda bir sorun oluştu.'))
      .mockResolvedValueOnce(makeStatus())
    const client = fakeDemoClient({ status })

    const { result } = renderHook(() => useWakeUp(client))
    await flush()
    await flush(WAKE_PAUSE_MS)

    expect(result.current.state.phase).toBe('ready')
  })

  it('deneme hakkı bitince DURUR: sınırsız yoklama yok, kullanıcı kontrollü yeniden deneme', async () => {
    const status = vi.fn().mockRejectedValue(new NetworkError('ulaşılamıyor'))
    const client = fakeDemoClient({ status })

    const { result } = renderHook(() => useWakeUp(client))
    await flush(WAKE_PAUSE_MS * (WAKE_ATTEMPTS + 2))

    expect(result.current.state).toMatchObject({ phase: 'failed', attempts: WAKE_ATTEMPTS })
    expect(status).toHaveBeenCalledTimes(WAKE_ATTEMPTS)
    await flush(10 * 60 * 1000) // 10 dakika daha geçse bile kendiliğinden yeni istek atılmaz
    expect(status).toHaveBeenCalledTimes(WAKE_ATTEMPTS)
  })

  it('retry() yeni bir bounded tur başlatır', async () => {
    const status = vi.fn().mockRejectedValue(new NetworkError('ulaşılamıyor'))
    const client = fakeDemoClient({ status })
    const { result } = renderHook(() => useWakeUp(client))
    await flush(WAKE_PAUSE_MS * (WAKE_ATTEMPTS + 1))
    expect(result.current.state.phase).toBe('failed')

    status.mockResolvedValue(makeStatus())
    act(() => result.current.retry())
    await flush()

    expect(result.current.state.phase).toBe('ready')
    expect(status).toHaveBeenCalledTimes(WAKE_ATTEMPTS + 1)
  })

  it('hazırlık isteği hiçbir koşulda karar ucunu çağırmaz', async () => {
    const client = fakeDemoClient()

    renderHook(() => useWakeUp(client))
    await flush()

    expect(client.decide).not.toHaveBeenCalled()
    expect(client.openSession).not.toHaveBeenCalled()
  })

  it('sayfa kapanınca (unmount) bekleyen deneme iptal edilir, istek atılmaz', async () => {
    const status = vi.fn().mockRejectedValue(new NetworkError('uyuyor'))
    const client = fakeDemoClient({ status })
    const { unmount } = renderHook(() => useWakeUp(client))
    await flush()
    expect(status).toHaveBeenCalledTimes(1)

    unmount()
    await flush(WAKE_PAUSE_MS * 5)

    expect(status).toHaveBeenCalledTimes(1)
  })
})

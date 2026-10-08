import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fakeDemoClient, makeResult, makeSession, makeSummary } from '../demo-fixtures'
import { ApiError, NetworkError } from '../lib/api'
import { readDemoToken, storeDemoToken } from '../lib/demo-api'
import type { DemoDecisionInput } from '../lib/demo-types'
import { CONNECTION_LOST_HELP, useDemoDecision } from './use-demo-decision'

const INPUT: DemoDecisionInput = {
  title: 'Lavabo akıtıyor',
  description: 'Su koridora yayılıyor, lütfen bakın.',
  location: 'B Blok',
}

beforeEach(() => storeDemoToken(null))

describe('useDemoDecision', () => {
  it('ilk gönderimde oturum açar, token saklar ve kararı gösterir', async () => {
    const client = fakeDemoClient()
    const { result } = renderHook(() => useDemoDecision(client, () => 1000))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(client.openSession).toHaveBeenCalledTimes(1)
    expect(readDemoToken()).toBe(makeSession().access_token)
    expect(client.decide).toHaveBeenCalledWith(INPUT)
    expect(result.current.run?.result.state).toBe('completed')
    expect(result.current.busy).toBe(false)
  })

  it('oturum varsa yeniden açılmaz', async () => {
    storeDemoToken('var-olan')
    const client = fakeDemoClient()
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(client.openSession).not.toHaveBeenCalled()
  })

  it('uçtan uca bekleme süresi bu isteğin gönderimi ile yanıtı arasındadır', async () => {
    let clock = 5000
    const client = fakeDemoClient({
      decide: vi.fn(async () => {
        clock += 1800
        return makeResult()
      }),
    })
    const { result } = renderHook(() => useDemoDecision(client, () => clock))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(result.current.run?.e2eMs).toBe(1800)
  })

  it('çift tıklama: uçuştaki istek varken ikinci gönderim HİÇ gönderilmez', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => (release = resolve))
    const client = fakeDemoClient({
      decide: vi.fn(async () => {
        await gate
        return makeResult()
      }),
    })
    const { result } = renderHook(() => useDemoDecision(client))

    let first!: Promise<void>
    act(() => {
      first = result.current.submit(INPUT)
    })
    await waitFor(() => expect(client.decide).toHaveBeenCalledTimes(1))
    await act(async () => {
      await result.current.submit(INPUT) // çift tıklama
      await result.current.submit(INPUT)
    })
    expect(client.decide).toHaveBeenCalledTimes(1)
    expect(result.current.busy).toBe(true)

    release()
    await act(async () => {
      await first
    })

    expect(client.decide).toHaveBeenCalledTimes(1)
    expect(result.current.busy).toBe(false)
  })

  it('401: oturumu yeniler ve BİR kez yeniden dener (işlenmeden reddedilen istek)', async () => {
    storeDemoToken('suresi-dolmus')
    const decide = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(401, 'unauthorized', 'Oturumun süresi dolmuş.'))
      .mockResolvedValueOnce(makeResult())
    const client = fakeDemoClient({ decide })
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(client.openSession).toHaveBeenCalledTimes(1)
    expect(decide).toHaveBeenCalledTimes(2)
    expect(readDemoToken()).toBe(makeSession().access_token)
    expect(result.current.run?.result.state).toBe('completed')
  })

  it('ikinci 401 döngüye girmez: hata gösterilir', async () => {
    const decide = vi.fn().mockRejectedValue(new ApiError(401, 'unauthorized', 'Oturum geçersiz.'))
    const client = fakeDemoClient({ decide })
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(decide).toHaveBeenCalledTimes(2) // en çok bir yeniden deneme
    expect(result.current.error).toBeInstanceOf(ApiError)
    expect(result.current.busy).toBe(false)
  })

  it('429 gibi sunucu mesajı olduğu gibi gösterilir ve yeniden denenmez', async () => {
    const decide = vi.fn().mockRejectedValue(new ApiError(429, 'demo_session_limit', 'Bu oturumda en çok 5 karar.'))
    const client = fakeDemoClient({ decide })
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(decide).toHaveBeenCalledTimes(1)
    expect(result.current.error?.message).toBe('Bu oturumda en çok 5 karar.')
    expect(result.current.run).toBeNull()
  })

  it('bağlantı kopması: sonuç kaydedilmiş olabileceği söylenir ve geçmiş yenilenir; otomatik yeniden gönderim yok', async () => {
    storeDemoToken('var')
    const decide = vi.fn().mockRejectedValue(new NetworkError('x', true))
    const listDecisions = vi.fn().mockResolvedValue([makeSummary()])
    const client = fakeDemoClient({ decide, listDecisions })
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(decide).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBeInstanceOf(NetworkError)
    expect(result.current.error?.message).toBe(CONNECTION_LOST_HELP)
    expect((result.current.error as NetworkError).timedOut).toBe(true)
    expect(result.current.history).toHaveLength(1)
  })

  it('check yalnızca OKUR: karar ucunu çağırmaz ve uçtan uca süre iddia etmez', async () => {
    storeDemoToken('var')
    const client = fakeDemoClient({ getDecision: vi.fn().mockResolvedValue(makeResult({ state: 'running' })) })
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.check('ticket-1')
    })

    expect(client.getDecision).toHaveBeenCalledWith('ticket-1')
    expect(client.decide).not.toHaveBeenCalled()
    expect(result.current.run?.e2eMs).toBeNull()
    expect(result.current.run?.result.state).toBe('running')
  })

  it('oturum yoksa geçmiş listesi sorgulanmaz', async () => {
    const client = fakeDemoClient()
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.refreshHistory()
    })

    expect(client.listDecisions).not.toHaveBeenCalled()
  })

  it('geçmiş listesi hatası ana akışı bozmaz', async () => {
    storeDemoToken('var')
    const client = fakeDemoClient({ listDecisions: vi.fn().mockRejectedValue(new Error('x')) })
    const { result } = renderHook(() => useDemoDecision(client))

    await act(async () => {
      await result.current.submit(INPUT)
    })

    expect(result.current.run?.result.state).toBe('completed')
    expect(result.current.error).toBeNull()
  })
})

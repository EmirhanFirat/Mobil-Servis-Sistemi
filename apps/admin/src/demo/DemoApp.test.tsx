import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RUN_ID, makeDetail, makeList, makeSample } from '../experiment-fixtures'
import { makeStatus } from '../demo-fixtures'
import { vocab } from '../test-utils'
import DemoApp from './DemoApp'

const experiments = {
  list: makeList(),
  details: { [RUN_ID]: makeDetail() },
  samples: { [RUN_ID]: { s023: makeSample() } },
}

let calls: string[] = []

beforeEach(() => {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = String(input)
      calls.push(url)
      const body = url.endsWith('/demo/status')
        ? makeStatus()
        : url.endsWith('experiments.json')
          ? experiments
          : url.endsWith('vocabulary.json')
            ? vocab
            : { detail: 'beklenmeyen istek' }
      const status = url.includes('beklenmeyen') ? 404 : 200
      return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.pushState({}, '', '/')
})

function open(path: string) {
  window.history.pushState({}, '', path === '/' ? '/' : '/#' + path)
  render(<DemoApp />)
  return userEvent.setup()
}

describe('DemoApp (herkese açık demo derlemesi)', () => {
  it('yalnızca demo ekranlarını gösterir: yönetici/oturum ekranları ve uçları YOK', async () => {
    open('/')

    expect(await screen.findByRole('heading', { name: 'Gerçek Jev ile dene' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ölçüm sonuçları' })).toBeInTheDocument()
    for (const adminOnly of ['Kullanıcılar', 'Ekipler', 'Talepler', 'Çıkış yap', 'Giriş yap']) {
      expect(screen.queryByText(adminOnly)).toBeNull()
    }
    await screen.findByTestId('wake-summary')
    expect(calls.some((url) => url.includes('/admin/') || url.includes('/auth/'))).toBe(false)
  })

  it('açılışta tek bir hazırlık isteği atılır; karar/oturum ucu çağrılmaz', async () => {
    open('/')
    await screen.findByTestId('wake-summary')

    const demoCalls = calls.filter((url) => url.includes('/demo/'))
    expect(demoCalls).toHaveLength(1)
    expect(demoCalls[0]).toMatch(/\/demo\/status$/)
  })

  it('"Ölçüm sonuçları" statik dosyadan açılır; API (uyanma) beklenmez, API çağrısı yapılmaz', async () => {
    const user = open('/sonuclar')

    expect(await screen.findByRole('heading', { name: 'Ölçüm sonuçları' })).toBeInTheDocument()
    expect((await screen.findAllByText(/5 sentetik geliştirme örneği/)).length).toBeGreaterThan(0)
    expect(screen.getByText(/statik bir dosyadan/)).toBeInTheDocument()
    expect(screen.getByText(/karıştırılmaz/)).toBeInTheDocument()
    expect(calls.some((url) => url.includes('/demo/') || url.includes('127.0.0.1:8000'))).toBe(false)
    expect(calls.every((url) => url.includes('demo-data/'))).toBe(true)

    await user.click(screen.getByRole('link', { name: 'Jev ile dene' }))
    expect(await screen.findByRole('heading', { name: 'Gerçek Jev ile dene' })).toBeInTheDocument()
  })

  it('bilinmeyen adres ana demo sayfasına yönlenir', async () => {
    open('/talepler/123')

    expect(await screen.findByRole('heading', { name: 'Gerçek Jev ile dene' })).toBeInTheDocument()
    await waitFor(() => expect(window.location.hash).toBe('#/'))
  })

  it('alt bilgide verinin Jev sağlayıcısına gittiği ve silindiği yazar', async () => {
    open('/')

    expect(await screen.findByText(/Jev API\s+sağlayıcısına gönderilir ve süre sonunda silinir/)).toBeInTheDocument()
  })

  it('statik sonuç dosyası yoksa açık hata ve yeniden dene (uydurma sonuç yok)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 404 })),
    )
    open('/sonuclar')

    expect(await screen.findByText(/okunamadı \(404\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tekrar dene' })).toBeInTheDocument()
    expect(screen.queryByText(/%100,0/)).toBeNull()
  })
})

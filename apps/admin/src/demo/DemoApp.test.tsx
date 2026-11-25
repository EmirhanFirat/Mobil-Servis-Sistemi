import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RUN_ID, makeDetail, makeList, makeSample } from '../experiment-fixtures'
import { makeStatus } from '../demo-fixtures'
import { vocab } from '../test-utils'
import DemoApp from './DemoApp'

const experiments = {
  list: makeList(),
  details: { [RUN_ID]: makeDetail() },
  samples: {
    [RUN_ID]: {
      s023: makeSample(),
      s003: { ...makeSample(), sample: { ...makeSample().sample, id: 's003', disputed: null } },
    },
  },
}

let calls: string[] = []
let demoStatus = makeStatus()
const scrollTo = vi.fn()

beforeEach(() => {
  calls = []
  demoStatus = makeStatus()
  scrollTo.mockClear()
  // jsdom window.scrollTo'yu uygulamaz; çağrıyı izlemek için yerine konur.
  vi.stubGlobal('scrollTo', scrollTo)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = String(input)
      calls.push(url)
      const body = url.endsWith('/demo/status')
        ? demoStatus
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
  it('tanıtım sayfasıyla açılır: lacivert menü, yönetici/oturum ekranları ve uçları YOK', async () => {
    open('/')

    expect(await screen.findByRole('heading', { level: 1, name: /Arıza bildirimi/ })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Demo sayfaları' })
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Tanıtım', 'Talep oluştur', 'Hakkında', 'Sonuçlar', 'Kaynak kod (GitHub)'])
    expect(screen.getByRole('link', { name: 'Talep bildir' })).toHaveAttribute('href', '#/talep')
    for (const adminOnly of ['Kullanıcılar', 'Ekipler', 'Talepler', 'Çıkış yap', 'Giriş yap']) {
      expect(screen.queryByText(adminOnly)).toBeNull()
    }
    expect(calls.some((url) => url.includes('/admin/') || url.includes('/auth/'))).toBe(false)
  })

  it('tanıtım açılışta sunucuyu yalnızca ücretsiz hazırlık isteğiyle uyandırır; karar/oturum yok', async () => {
    open('/')

    await waitFor(() => expect(calls.some((url) => url.endsWith('/demo/status'))).toBe(true))
    const demoCalls = calls.filter((url) => url.includes('/demo/'))
    expect(demoCalls).toEqual([expect.stringMatching(/\/demo\/status$/)])
  })

  it('tanıtımdaki görsel yerel dosyadan gelir ve açıklayıcı alt metni vardır', async () => {
    open('/')

    const image = await screen.findByRole('img', { name: /bakım görevlisi/ })
    expect(image.getAttribute('src')).toMatch(/anasayfa-1400/)
    expect(image.getAttribute('src')).not.toMatch(/^https?:/)
  })

  it('hızlı başlangıç kutusuna yazılan cümle talep formunun başlığına taşınır', async () => {
    const user = open('/')

    await user.type(await screen.findByLabelText('Sorunu bir cümleyle yaz'), 'Koridor lambası yanmıyor')
    await user.click(within(screen.getByRole('form', { name: 'Hızlı başlangıç' })).getByRole('button'))

    expect(await screen.findByRole('heading', { name: 'Kampüste bir sorun mu var?' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Ne oldu\?/)).toHaveValue('Koridor lambası yanmıyor')
    expect(window.location.hash).toBe('#/talep')
    expect(calls.some((url) => url.includes('/demo/decisions'))).toBe(false) // gönderilmedi, yalnızca dolduruldu
  })

  it('"Talep oluştur" sayfasında tek hazırlık isteği atılır; karar/oturum ucu çağrılmaz', async () => {
    open('/talep')
    await screen.findByTestId('wake-summary')

    const demoCalls = calls.filter((url) => url.includes('/demo/'))
    expect(demoCalls).toHaveLength(1)
    expect(demoCalls[0]).toMatch(/\/demo\/status$/)
    expect(screen.queryByRole('link', { name: 'Talep bildir' })).toBeNull() // zaten formdayız
  })

  it('"Ölçüm sonuçları" statik dosyadan açılır; API (uyanma) beklenmez, API çağrısı yapılmaz', async () => {
    const user = open('/sonuclar')

    expect(await screen.findByRole('heading', { name: 'Ölçüm sonuçları' })).toBeInTheDocument()
    expect((await screen.findAllByText(/5 sentetik geliştirme örneği/)).length).toBeGreaterThan(0)
    expect(screen.getByText(/statik bir dosyadan/)).toBeInTheDocument()
    expect(screen.getByText(/karıştırılmaz/)).toBeInTheDocument()
    expect(calls.some((url) => url.includes('/demo/') || url.includes('127.0.0.1:8000'))).toBe(false)
    expect(calls.every((url) => url.includes('demo-data/'))).toBe(true)

    const nav = screen.getByRole('navigation', { name: 'Demo sayfaları' })
    await user.click(within(nav).getByRole('link', { name: 'Talep oluştur' }))
    expect(await screen.findByRole('heading', { name: 'Kampüste bir sorun mu var?' })).toBeInTheDocument()
  })

  it('bilinmeyen adres tanıtım sayfasına yönlenir', async () => {
    open('/talepler/123')

    expect(await screen.findByRole('heading', { level: 1, name: /Arıza bildirimi/ })).toBeInTheDocument()
    await waitFor(() => expect(window.location.hash).toBe('#/'))
  })

  it('verinin nereye gittiği ve silindiği formun altında yazar; alt bilgide demo notu ve 112 var', async () => {
    open('/talep')

    const disclosure = await screen.findByTestId('disclosure')
    expect(disclosure).toHaveTextContent('Jev API sağlayıcısına gönderilir')
    expect(disclosure).toHaveTextContent('72 saat sonra otomatik silinir')
    const footer = screen.getByRole('contentinfo')
    expect(footer).toHaveTextContent('Portföy demosu')
    expect(footer).toHaveTextContent('Talepler gerçek bir ekibe iletilmez.')
    expect(footer).toHaveTextContent('112')
  })

  it('kaynak kod bağlantısı GitHub ikonuyla, erişilebilir adla gelir', async () => {
    open('/')

    const links = await screen.findAllByRole('link', { name: 'Kaynak kod (GitHub)' })
    for (const link of links) {
      expect(link).toHaveAttribute('href', 'https://github.com/EmirhanFirat/Mobil-Servis-Sistemi')
    }
    expect(links.some((link) => link.querySelector('svg') !== null)).toBe(true)
  })

  it('mobil menü düğmesi menüyü açar; sayfa değişince menü kapanır', async () => {
    const user = open('/')
    const toggle = await screen.findByRole('button', { name: 'Menüyü aç' })
    const nav = screen.getByRole('navigation', { name: 'Demo sayfaları' })
    expect(toggle).toHaveAttribute('aria-controls', nav.id)

    await user.click(toggle)
    expect(screen.getByRole('button', { name: 'Menüyü kapat' })).toHaveAttribute('aria-expanded', 'true')
    expect(nav).toHaveClass('open')

    await user.click(within(nav).getByRole('link', { name: 'Hakkında' }))
    expect(await screen.findByRole('heading', { name: 'TalepAkış hakkında' })).toBeInTheDocument()
    expect(nav).not.toHaveClass('open')
    expect(screen.getByRole('button', { name: 'Menüyü aç' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('sekme değişince sayfa en üstten açılır (HashRouter kaydırmayı korumaz)', async () => {
    const user = open('/')
    await screen.findByRole('heading', { level: 1, name: /Arıza bildirimi/ })
    scrollTo.mockClear()

    const nav = screen.getByRole('navigation', { name: 'Demo sayfaları' })
    await user.click(within(nav).getByRole('link', { name: 'Sonuçlar' }))
    expect(await screen.findByRole('heading', { name: 'Ölçüm sonuçları' })).toBeInTheDocument()
    expect(scrollTo).toHaveBeenCalledWith(0, 0)

    scrollTo.mockClear()
    await user.click(within(nav).getByRole('link', { name: 'Talep oluştur' }))
    await screen.findByRole('heading', { name: 'Kampüste bir sorun mu var?' })
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it('"Hakkında" projeyi anlatır ve statik dosyadaki kayıtlı örnek kartını gösterir; API çağrısı yok', async () => {
    open('/hakkinda')

    expect(await screen.findByRole('heading', { name: 'TalepAkış hakkında' })).toBeInTheDocument()
    const card = await screen.findByRole('region', { name: 'Kayıtlı örnek' })
    expect(card).toHaveTextContent('Kayıtlı örnek ·')
    expect(calls.some((url) => url.includes('/demo/'))).toBe(false)
  })

  it('talep sayfası şikâyet formudur: kayıtlı örnek orada yer almaz', async () => {
    demoStatus = makeStatus({ enabled: false, reason: 'not_configured', accepting: true, engine: 'rules' })
    open('/talep')

    await screen.findByTestId('wake-summary')
    expect(screen.getByRole('form', { name: 'Talep formu' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Kayıtlı örnek' })).toBeNull()
    expect(calls.some((url) => url.includes('/demo/decisions') || url.includes('/demo/session'))).toBe(false)
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

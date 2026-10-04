import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RUN_ID, makeDetail, makeList, makeRun, makeSample } from '../experiment-fixtures'
import { ApiError, type ApiClient } from '../lib/api'
import { AuthContext, type AuthValue } from '../lib/auth-context'
import { downloadBlob, downloadText, svgToPngBlob } from '../lib/image-export'
import { fakeApi, vocab } from '../test-utils'
import ModelComparisonPage from './ModelComparisonPage'

vi.mock('../lib/image-export', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/image-export')>()
  return { ...original, downloadText: vi.fn(), downloadBlob: vi.fn(), svgToPngBlob: vi.fn() }
})

const admin = {
  id: 'u-admin',
  username: 'yonetici',
  display_name: 'Zeynep Yönetici',
  role: 'admin' as const,
  is_active: true,
  teams: [],
}

function experimentApi(overrides: Record<string, unknown> = {}): ApiClient {
  return fakeApi({
    listExperiments: vi.fn().mockResolvedValue(makeList()),
    getExperiment: vi.fn().mockResolvedValue(makeDetail()),
    getExperimentSample: vi.fn().mockResolvedValue(makeSample()),
    ...overrides,
  })
}

function renderPage(api: ApiClient, initial = '/model-karsilastirma') {
  const value: AuthValue = {
    status: 'signedIn',
    user: admin,
    vocab,
    api,
    notice: null,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    retry: vi.fn(),
  }
  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[initial]}>
        <ModelComparisonPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return userEvent.setup()
}

function mutatingCalls(api: ApiClient): number {
  const a = api as unknown as Record<string, ReturnType<typeof vi.fn>>
  return ['assign', 'patchTicket', 'transition'].reduce((sum, key) => sum + a[key].mock.calls.length, 0)
}

beforeEach(() => vi.clearAllMocks())

describe('boş, eksik ve hatalı durumlar', () => {
  it('deney klasörü yoksa açık boş durum gösterir; rakam uydurmaz', async () => {
    const api = experimentApi({ listExperiments: vi.fn().mockResolvedValue(makeList([], false)) })
    renderPage(api)

    expect(await screen.findByText('Kayıtlı deney bulunamadı')).toBeInTheDocument()
    expect(screen.getByText(/evaluation\/runs klasörü bulunamadı/)).toBeInTheDocument()
    expect(screen.getByText(/uydurma rakam göstermez/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(api.getExperiment).not.toHaveBeenCalled()
  })

  it('klasör var ama boşsa bunu söyler', async () => {
    renderPage(experimentApi({ listExperiments: vi.fn().mockResolvedValue(makeList([], true)) }))

    expect(await screen.findByText(/evaluation\/runs klasörü boş/)).toBeInTheDocument()
  })

  it('yönetici olmayan erişim reddi "Erişim yok" olarak gösterilir', async () => {
    const denied = new ApiError(403, null, 'Bu işlem yalnızca yöneticiler içindir.')
    renderPage(experimentApi({ listExperiments: vi.fn().mockRejectedValue(denied) }))

    expect(await screen.findByText('Erişim yok')).toBeInTheDocument()
    expect(screen.getByText('Bu işlem yalnızca yöneticiler içindir.')).toBeInTheDocument()
  })

  it('metrikler hesaplanamıyorsa nedenini söyler ve tablo göstermez', async () => {
    const detail = makeDetail({
      metrics_available: false,
      unavailable_reason: 'predictions.jsonl bulunamadı; bu deney için rakam gösterilemez.',
      strategies: [],
      samples: [],
      warnings: [],
    })
    renderPage(experimentApi({ getExperiment: vi.fn().mockResolvedValue(detail) }))

    expect(await screen.findByText(/Bu deney için rakam gösterilemiyor/)).toBeInTheDocument()
    expect(screen.getByText(/predictions\.jsonl bulunamadı/)).toBeInTheDocument()
    expect(screen.getByText('Gösterilecek ölçüm yok')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'CSV indir' })).not.toBeInTheDocument()
  })

  it('deney ayrıntısı yüklenemezse hata ve yeniden deneme sunar', async () => {
    const getExperiment = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(404, 'not_found', 'Deney bulunamadı.'))
      .mockResolvedValue(makeDetail())
    const user = renderPage(experimentApi({ getExperiment }))

    expect(await screen.findByText('Deney bulunamadı.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Tekrar dene' }))

    expect(await screen.findByRole('table', { name: 'Strateji karşılaştırması' })).toBeInTheDocument()
  })
})

describe('deney seçici', () => {
  it('seçicide tarih, örnek kapsamı, stratejiler, tamamlanma ve deney sürümü görünür', async () => {
    renderPage(experimentApi())

    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })

    const option = screen.getByRole('option')
    expect(option).toHaveTextContent('02.10.2026')
    expect(option).toHaveTextContent('5 sentetik geliştirme örneği — bağlantı denemesi')
    expect(option).toHaveTextContent('Jev + LLM + Hibrit')
    expect(option).toHaveTextContent('Tamamlandı')
    const facts = screen.getByLabelText('Kayıtlı deney').closest('section') as HTMLElement
    expect(within(facts).getByText(/5\/5 örnek/)).toBeInTheDocument()
    expect(within(facts).getByText(/Hibrit v1 — kayıtta sürüm yok, eski yönlendirme/)).toBeInTheDocument()
    expect(within(facts).getByText(/kaynak commit 09584e9/)).toBeInTheDocument()
  })

  it('en yeni TAMAMLANMIŞ deneyi varsayılan açar; yarım deney seçilebilir ve durumu görünür', async () => {
    const partial = makeRun({
      id: '20261003T090000Z-v1-dev',
      created_at: '2026-10-03T09:00:00+00:00',
      status: 'partial',
      status_detail: 'Çalıştırma yarıda kaldı (3/5 örnek): bütçe.',
    })
    const api = experimentApi({
      listExperiments: vi.fn().mockResolvedValue(makeList([partial, makeRun()])),
    })
    const user = renderPage(api)

    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })
    expect(api.getExperiment).toHaveBeenCalledWith(RUN_ID)

    await user.selectOptions(screen.getByLabelText('Kayıtlı deney'), partial.id)

    await waitFor(() => expect(api.getExperiment).toHaveBeenCalledWith(partial.id))
    expect(await screen.findByText(/Yarım kaldı/, { selector: 'span.badge' })).toBeInTheDocument()
    expect(screen.getByText(/Çalıştırma yarıda kaldı \(3\/5 örnek\)/)).toBeInTheDocument()
  })

  it('adres parametresiyle belirtilen deney açılır', async () => {
    const other = makeRun({
      id: '20261001T100000Z-v1-dev',
      created_at: '2026-10-01T10:00:00+00:00',
    })
    const api = experimentApi({
      listExperiments: vi.fn().mockResolvedValue(makeList([makeRun(), other])),
    })

    renderPage(api, `/model-karsilastirma?deney=${other.id}`)

    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })
    expect(api.getExperiment).toHaveBeenCalledWith(other.id)
    expect(api.getExperiment).not.toHaveBeenCalledWith(RUN_ID)
  })
})

describe('karşılaştırma ekranı', () => {
  it('stratejileri yan yana ve ölçülen ile tahmini ayrı gösterir', async () => {
    renderPage(experimentApi())

    const table = await screen.findByRole('table', { name: 'Strateji karşılaştırması' })

    for (const name of ['Jev', 'LLM', 'Hibrit']) {
      expect(within(table).getByRole('columnheader', { name: new RegExp(name) })).toBeInTheDocument()
    }
    expect(within(table).getByText('Kategori doğruluğu')).toBeInTheDocument()
    expect(within(table).getByText('Toplam bilinen model ücreti (ölçülen)')).toBeInTheDocument()
    expect(within(table).getByText('1.000 talebe ölçeklenen TAHMİN')).toBeInTheDocument()
    expect(within(table).getByText('2,9420 USD (tahmin)')).toBeInTheDocument()
    expect(within(table).getByText('0,01471 USD')).toBeInTheDocument()
    expect(within(table).getByText('902 (tamamı ücretsiz çıktı)')).toBeInTheDocument()
    expect(screen.getAllByText(/tokenizer/).length).toBeGreaterThan(0)
  })

  it('uyarılar: küçük örneklem, eski hibrit sürümü ve tartışmalı etiket', async () => {
    renderPage(experimentApi())

    expect(await screen.findByText(/Küçük örneklem \(5 örnek\)/)).toBeInTheDocument()
    expect(screen.getByText(/hibrit yönlendirme v1 ile alındı/)).toBeInTheDocument()
    expect(screen.getByText(/v2'nin daha iyi olduğuna dair henüz gerçek ölçüm yoktur/)).toBeInTheDocument()
    expect(screen.getByText(/Tartışmalı etiketli örnek: s023/)).toBeInTheDocument()
  })

  it('uyarı tonu: bilgilendirme (küçük örneklem, eski sürüm) ile dikkat gerektiren (tartışmalı etiket) ayrışır', async () => {
    renderPage(experimentApi())

    const small = (await screen.findByText(/Küçük örneklem \(5 örnek\)/)).closest('.notice')
    const disputed = screen.getByText(/Tartışmalı etiketli örnek: s023/).closest('.notice')

    expect(small).toHaveClass('notice-info')
    expect(small).toHaveAttribute('role', 'status')
    expect(disputed).toHaveClass('notice-error')
    expect(disputed).toHaveAttribute('role', 'alert')
  })

  it('ücret ve gecikme ayrı grafiklerdir', async () => {
    renderPage(experimentApi())
    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })

    expect(screen.getAllByRole('img', { name: 'Tamamlanan talep başına ölçülen ücret' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('img', { name: 'Uçtan uca karar süresi' }).length).toBeGreaterThan(0)
  })

  it('harcama dökümü karşılaştırma dışı harcamayı gizlemez; defter yalnızca okunur', async () => {
    const detail = makeDetail({
      reconciliation: {
        compared_known_usd: '0.0210',
        run_known_spent_usd: '0.0214',
        outside_comparison_usd: '0.0004',
        conservative_spent_usd: '0',
      },
    })
    renderPage(experimentApi({ getExperiment: vi.fn().mockResolvedValue(detail) }))

    expect(await screen.findByText('Harcama dökümü')).toBeInTheDocument()
    expect(screen.getByText(/0,0004 USD \(yarım\/ortak olmayan örnekler; toplamdan gizlenmez\)/)).toBeInTheDocument()
    expect(screen.getByText(/ilk-deneme · sınır 0,1000 USD · kalan 0,078623348 USD/)).toBeInTheDocument()
    expect(screen.getByText(/defteri yalnızca okur/)).toBeInTheDocument()
  })

  it('deney koşulları: sürümler, eşikler ve fiyatların kontrol tarihi', async () => {
    const user = renderPage(experimentApi())
    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })

    await user.click(screen.getByText('Deney koşulları (doğrudan kıyas için)'))

    expect(screen.getByText(/AYNI deneydeki stratejileri karşılaştırır/)).toBeInTheDocument()
    expect(screen.getByText(/Jev güven eşikleri: category=0\.6/)).toBeInTheDocument()
    expect(screen.getByText(/tetikleyebilen soru listesi kayıtta yok \(v1: tüm sorular\)/)).toBeInTheDocument()
    expect(screen.getAllByText(/kontrol 2026-10-02/).length).toBe(2)
  })
})

describe('örnek bazında inceleme', () => {
  async function openSamples() {
    const api = experimentApi()
    const user = renderPage(api)
    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })
    await user.click(screen.getByRole('tab', { name: 'Örnek bazında inceleme' }))
    return { api, user }
  }

  it('örnek tablosu beklenen etiketi ve her stratejinin tahminini gösterir; s023 tartışmalı işaretli', async () => {
    await openSamples()

    const table = await screen.findByRole('table', { name: 'Örnek bazında karşılaştırma' })
    const s023 = within(table).getByRole('button', { name: 's023 örneğini incele' }).closest('tr') as HTMLElement

    expect(within(s023).getByText('Tartışmalı etiket')).toBeInTheDocument()
    expect(within(s023).getByText(/Diğer · Normal/)).toBeInTheDocument()
    expect(within(s023).getAllByText(/Diğer \(doğru\) · Yüksek \(yanlış\)/)).toHaveLength(3)
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5)
  })

  it('süzgeç yalnızca tartışmalı / yanlış tahmin edilen örnekleri bırakır', async () => {
    const { user } = await openSamples()
    const table = await screen.findByRole('table', { name: 'Örnek bazında karşılaştırma' })

    await user.selectOptions(screen.getByLabelText('Örnek süzgeci'), 'disputed')
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 1)
    expect(within(table).getByText('Asansör bozuk')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Örnek süzgeci'), 'review')
    expect(within(table).getByText('Bu süzgeçte örnek yok.')).toBeInTheDocument()
  })

  it('örneğe tıklayınca tam metin, beklenen etiket ve üç stratejinin tahmini yan yana açılır', async () => {
    const { api, user } = await openSamples()

    await user.click(await screen.findByRole('button', { name: 's023 örneğini incele' }))

    const inspector = await screen.findByRole('region', { name: 's023 örnek ayrıntısı' })
    expect(api.getExperimentSample).toHaveBeenCalledWith(RUN_ID, 's023')
    expect(within(inspector).getByText('Asansör kapısı kapanmıyor, kata gelince açılmıyor.')).toBeInTheDocument()
    expect(
      within(inspector).getByText(/Kategori: Diğer · Öncelik: Normal · İnceleme beklenir: hayır/),
    ).toBeInTheDocument()
    expect(within(inspector).getByText(/tek kişiyce yazıldı, gözden geçirilmedi/)).toBeInTheDocument()
    expect(within(inspector).getByText(/Tartışmalı etiket \(gözden geçirme bekliyor\)/)).toBeInTheDocument()
    expect(within(inspector).getByText(/Etiketler ve geçmiş deney sonuçları değiştirilmedi/)).toBeInTheDocument()
    for (const name of ['Jev', 'LLM', 'Hibrit']) {
      expect(within(inspector).getByRole('region', { name })).toBeInTheDocument()
    }
    const hybrid = within(inspector).getByRole('region', { name: 'Hibrit' })
    // LLM'e aktarılan sorular satırı
    const escalated = within(hybrid).getByText("LLM'e aktarılan sorular")
    expect(escalated.nextElementSibling).toHaveTextContent('İletişim bilgisi eksik mi?')
    expect(within(hybrid).getByText('1.151 ms')).toBeInTheDocument() // karar süresi
  })

  it('güven türleri ayrı kavram olarak adlandırılır; modelin yazmadığı gerekçe gösterilmez', async () => {
    const { user } = await openSamples()
    await user.click(await screen.findByRole('button', { name: 's023 örneğini incele' }))
    const inspector = await screen.findByRole('region', { name: 's023 örnek ayrıntısı' })

    expect(within(inspector).getAllByText(/1,00 \(Jev güveni\)/).length).toBeGreaterThan(0)
    expect(within(inspector).getAllByText(/0,95 \(modelin kendi yazdığı, kalibre değil\)/).length).toBeGreaterThan(0)
    expect(within(inspector).getAllByText(/0,52 \(olasılıktan türetilmiş\)/).length).toBeGreaterThan(0)
    expect(within(inspector).getAllByText(/Güven değerleri farklı kavramlardır/).length).toBeGreaterThan(0)
    expect(within(inspector).getAllByText(/\(karara alınmadı\)/).length).toBeGreaterThan(0)
    expect(inspector.textContent).not.toMatch(/gerekçe:|Gerekçe:/)
  })

  it('örnek ayrıntısı yüklenemezse hata gösterir ve kapatılabilir', async () => {
    const api = experimentApi({
      getExperimentSample: vi.fn().mockRejectedValue(new ApiError(404, 'not_found', 'Örnek bulunamadı.')),
    })
    const user = renderPage(api)
    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })
    await user.click(screen.getByRole('tab', { name: 'Örnek bazında inceleme' }))

    await user.click(await screen.findByRole('button', { name: 's003 örneğini incele' }))

    expect(await screen.findByText('Örnek bulunamadı.')).toBeInTheDocument()
  })
})

describe('paylaşım görünümü ve dışa aktarma', () => {
  async function openShare() {
    const api = experimentApi()
    const user = renderPage(api)
    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })
    await user.click(screen.getByRole('tab', { name: 'Paylaşım görünümü' }))
    await screen.findByTestId('share-card')
    return { api, user }
  }

  it('paylaşım kartı veri kaynağı, örnek sayısı, tarih ve sürümleri taşır', async () => {
    await openShare()

    const card = screen.getByTestId('share-card')
    const content = Array.from(card.querySelectorAll('text'))
      .map((n) => n.textContent)
      .join(' ')

    expect(content).toContain('5 sentetik geliştirme örneği — bağlantı denemesi')
    expect(content).toContain('Veri kaynağı: sentetik veri seti v1')
    expect(content).toContain('Hibrit v1 — kayıtta sürüm yok, eski yönlendirme')
  })

  it('görseldeki örnek talep seçilebilir; varsayılan ortak örnek yüklenir', async () => {
    const { api, user } = await openShare()

    await waitFor(() => expect(api.getExperimentSample).toHaveBeenCalledWith(RUN_ID, 's003'))
    await user.selectOptions(screen.getByLabelText('Örnek talep'), 's023')

    await waitFor(() => expect(api.getExperimentSample).toHaveBeenCalledWith(RUN_ID, 's023'))
    expect(screen.getByRole('option', { name: /s023 · Asansör bozuk \(tartışmalı etiket\)/ })).toBeInTheDocument()
  })

  it('CSV ve Markdown indirme yüklü verilerden üretilir ve hiçbir API çağrısı başlatmaz', async () => {
    const { api, user } = await openShare()
    const callsBefore = {
      list: (api.listExperiments as ReturnType<typeof vi.fn>).mock.calls.length,
      detail: (api.getExperiment as ReturnType<typeof vi.fn>).mock.calls.length,
      sample: (api.getExperimentSample as ReturnType<typeof vi.fn>).mock.calls.length,
    }

    await user.click(screen.getByRole('button', { name: 'CSV indir' }))
    await user.click(screen.getByRole('button', { name: 'Markdown tablo indir' }))

    expect(downloadText).toHaveBeenCalledTimes(2)
    const [csv, csvName, csvMime] = vi.mocked(downloadText).mock.calls[0]
    expect(csvName).toBe(`model-karsilastirma-${RUN_ID}.csv`)
    expect(csvMime).toBe('text/csv')
    expect(csv).toContain('olculen_toplam_ucret_usd')
    const [md, mdName] = vi.mocked(downloadText).mock.calls[1]
    expect(mdName).toBe(`model-karsilastirma-${RUN_ID}.md`)
    expect(md).toContain('| Ölçüt | Jev | LLM | Hibrit |')
    expect((api.listExperiments as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(callsBefore.list)
    expect((api.getExperiment as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(callsBefore.detail)
    expect((api.getExperimentSample as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(callsBefore.sample)
    expect(mutatingCalls(api)).toBe(0)
  })

  it('PNG indirme SVG kartını görsele çevirip doğru adla indirir', async () => {
    const { user } = await openShare()
    const blob = new Blob(['png'], { type: 'image/png' })
    vi.mocked(svgToPngBlob).mockResolvedValue(blob)

    await user.click(screen.getByRole('button', { name: 'PNG indir' }))

    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(blob, `model-karsilastirma-${RUN_ID}.png`))
    expect(vi.mocked(svgToPngBlob).mock.calls[0][0]).toBe(screen.getByTestId('share-card'))
    expect(vi.mocked(svgToPngBlob).mock.calls[0][1]).toBe(2)
  })

  it('PNG üretimi başarısız olursa kullanıcıya hata gösterilir', async () => {
    const { user } = await openShare()
    vi.mocked(svgToPngBlob).mockRejectedValue(new Error('Tarayıcı görsel üretemiyor.'))

    await user.click(screen.getByRole('button', { name: 'PNG indir' }))

    expect(await screen.findByText('Tarayıcı görsel üretemiyor.')).toBeInTheDocument()
    expect(downloadBlob).not.toHaveBeenCalled()
  })
})

describe('yalnızca okuma', () => {
  it('sayfayı açmak, sekme değiştirmek, süzmek ve dışa aktarmak yalnızca GET uçlarını kullanır', async () => {
    const api = experimentApi()
    const user = renderPage(api)
    await screen.findByRole('table', { name: 'Strateji karşılaştırması' })

    await user.click(screen.getByRole('tab', { name: 'Örnek bazında inceleme' }))
    await user.selectOptions(await screen.findByLabelText('Örnek süzgeci'), 'wrong')
    await user.click(screen.getByRole('tab', { name: 'Paylaşım görünümü' }))
    await screen.findByTestId('share-card')
    await user.click(screen.getByRole('button', { name: 'CSV indir' }))

    expect(mutatingCalls(api)).toBe(0)
    // Deney listesi ve ayrıntısı yalnızca bir kez istendi (sekme/süzgeç yeniden yüklemez).
    expect(api.listExperiments).toHaveBeenCalledTimes(1)
    expect(api.getExperiment).toHaveBeenCalledTimes(1)
  })
})

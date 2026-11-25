import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fakeDemoClient, makeResult, makeStatus, makeSummary } from '../demo-fixtures'
import { ApiError } from '../lib/api'
import { storeDemoToken, type DemoClient } from '../lib/demo-api'
import type { DemoDecisionResult } from '../lib/demo-types'
import { vocab } from '../test-utils'
import DemoPage from './DemoPage'

beforeEach(() => storeDemoToken(null))

async function renderReady(client: DemoClient = fakeDemoClient()) {
  const user = userEvent.setup()
  render(<DemoPage client={client} vocab={vocab} />)
  await screen.findByTestId('wake-summary')
  return { user, client }
}

const submitButton = () => screen.getByRole('button', { name: /Talebi gönder|Gönderiliyor/ })
const titleField = () => screen.getByLabelText(/^Ne oldu\?/)
const descriptionField = () => screen.getByLabelText(/^Ayrıntılar/)
const locationField = () => screen.getByLabelText(/^Nerede\?/)
const topic = (name: RegExp) => screen.getByRole('button', { name })
const receipt = () => screen.findByRole('region', { name: 'Talep fişi' })

/** Kural tabanlı motorun karşıladığı tamamlanmış talep (Jev kapalı; model çağrısı yok). */
function ruleResult(overrides: Partial<DemoDecisionResult> = {}): DemoDecisionResult {
  const base = makeResult()
  return makeResult({
    engine: 'rules',
    message:
      'Talebin kural tabanlı ön değerlendirmeyle karşılandı. Yapay zekâ (Jev) şu an kapalı; ücretli çağrı yapılmadı.',
    decision: { ...base.decision!, provider: 'rule_based', model: 'rules-v1', judgments: [] },
    usage: null,
    timings: { jev_call_ms: null, job_ms: 12, server_total_ms: 40 },
    ...overrides,
  })
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Lavabo akıtıyor' }))
  await user.click(submitButton())
}

describe('DemoPage: portal açılışı', () => {
  it('şikâyet portalı olarak açılır: başlık, konu kartları ve form; demo uyarısı 112 ve silinmeyi söyler', async () => {
    await renderReady()

    expect(screen.getByRole('heading', { level: 1, name: 'Kampüste bir sorun mu var?' })).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Talep formu' })).toBeInTheDocument()
    for (const name of [/Su \/ Tesisat/, /Elektrik/, /İnternet \/ BT/, /Temizlik/, /Emin değilim/]) {
      expect(topic(name)).toHaveAttribute('aria-pressed', 'false')
    }
    const banner = screen.getByRole('note')
    expect(banner).toHaveTextContent('gerçek bir bakım ekibine iletilmez')
    expect(banner).toHaveTextContent('72 saat')
    expect(banner).toHaveTextContent('112')
    expect(within(banner).getByRole('link', { name: /Proje hakkında/ })).toHaveAttribute('href', '#/hakkinda')
    // Araştırma anlatımı ve kayıtlı örnek ana sayfada değil, "Hakkında"dadır.
    expect(screen.queryByRole('region', { name: 'Kayıtlı örnek' })).toBeNull()
  })

  it('verinin nereye gittiği ve silindiği katlanan notta yazar', async () => {
    await renderReady()

    const disclosure = screen.getByTestId('disclosure')
    expect(disclosure.tagName).toBe('DETAILS')
    expect(disclosure).toHaveTextContent('Jev API sağlayıcısına gönderilir')
    expect(disclosure).toHaveTextContent('72 saat sonra otomatik silinir')
  })

  it('hazır olunca "Sunucu hazır" rozeti; uyanma süresi rozetin içinde, model süresinden ayrı', async () => {
    await renderReady(fakeDemoClient({ status: vi.fn().mockResolvedValue(makeStatus({ database_ms: 900 })) }))

    const badge = screen.getByTestId('wake-summary')
    expect(badge.tagName).toBe('DETAILS')
    expect(badge).not.toHaveAttribute('open')
    expect(within(badge).getByText('Sunucu hazır')).toBeInTheDocument()
    expect(badge).toHaveTextContent('İlk istekten hazır olana kadar geçen süre')
    expect(badge).toHaveTextContent('Jev çağrı süresi değildir')
  })

  it('sunucu uyanırken form doldurulabilir ama gönderilemez; hazırlık isteği model çağırmaz', async () => {
    const user = userEvent.setup()
    const client = fakeDemoClient({ status: vi.fn(() => new Promise(() => {})) })
    render(<DemoPage client={client} vocab={vocab} />)

    expect(await screen.findByText(/Sunucu hazırlanıyor…/)).toHaveTextContent('model çağrısı yapmaz')
    await user.type(titleField(), 'Priz yanıyor')
    expect(titleField()).toHaveValue('Priz yanıyor')
    expect(submitButton()).toBeDisabled()
    expect(submitButton()).toHaveAttribute('aria-describedby', 'submit-reason')
    expect(screen.getByText(/bu sırada formu doldurabilirsin/)).toBeInTheDocument()
    expect(client.decide).not.toHaveBeenCalled()
  })

  it('Jev açıkken talebin yapay zekâ ile değerlendirileceği yazar', async () => {
    await renderReady()

    expect(screen.getByText(/yapay zekâ \(Jev\) ile ön değerlendirilir/)).toBeInTheDocument()
    expect(submitButton()).toBeEnabled()
  })

  it('Jev kapalı ama talep alınıyorsa: form açık, kural tabanlı karşılanacağı açıkça yazar (hata değil)', async () => {
    await renderReady(
      fakeDemoClient({
        status: vi
          .fn()
          .mockResolvedValue(
            makeStatus({ enabled: false, reason: 'not_configured', accepting: true, engine: 'rules' }),
          ),
      }),
    )

    expect(screen.getByText(/Yapay zekâ şu an kapalı; talebin kural tabanlı/)).toHaveTextContent('model çağrısı yok')
    expect(submitButton()).toBeEnabled()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(document.querySelector('.notice-error')).toBeNull()
  })

  it('talep alımı kapalıysa (acil durdurma) nötr bilgi; alanlar ve gönderme kapalı', async () => {
    const client = fakeDemoClient({
      status: vi
        .fn()
        .mockResolvedValue(makeStatus({ enabled: false, reason: 'disabled', accepting: false, engine: null })),
    })
    await renderReady(client)

    const notice = screen.getByText('Talep alımı şu an kapalı.', { selector: 'strong' }).closest('.notice')!
    expect(notice).toHaveClass('notice-info')
    expect(within(notice as HTMLElement).getByRole('link', { name: 'Ölçüm sonuçları' })).toHaveAttribute(
      'href',
      '#/sonuclar',
    )
    expect(submitButton()).toBeDisabled()
    expect(titleField()).toBeDisabled()
    expect(topic(/Elektrik/)).toBeDisabled()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(client.decide).not.toHaveBeenCalled()
  })

  it('MOCK kurulumda "gerçek ölçüm değil" uyarısı görünür', async () => {
    await renderReady(
      fakeDemoClient({ status: vi.fn().mockResolvedValue(makeStatus({ is_mock: true, provider: 'mock-jev' })) }),
    )

    expect(screen.getAllByText(/gerçek ölçüm değildir/).length).toBeGreaterThan(0)
  })

  it('sunucuya hiç ulaşılamazsa hata ve kullanıcı kontrollü yeniden dene', async () => {
    vi.useFakeTimers()
    try {
      const client = fakeDemoClient({ status: vi.fn().mockRejectedValue(new Error('ulaşılamıyor')) })
      render(<DemoPage client={client} vocab={vocab} />)
      await vi.advanceTimersByTimeAsync(60_000)

      expect(screen.getByRole('button', { name: 'Yeniden dene' })).toBeInTheDocument()
      expect(screen.getByText(/sayfa kendiliğinden sürekli denemez/)).toBeInTheDocument()
      expect(submitButton()).toBeDisabled()
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('DemoPage: form', () => {
  it('konu seçimi yalnızca ipucunu değiştirir; karar isteğine konu GİTMEZ', async () => {
    const { user, client } = await renderReady()

    await user.click(topic(/Elektrik/))
    expect(topic(/Elektrik/)).toHaveAttribute('aria-pressed', 'true')
    expect(titleField()).toHaveAttribute('placeholder', 'ör. Koridor lambası yanmıyor')
    await user.click(topic(/Elektrik/))
    expect(topic(/Elektrik/)).toHaveAttribute('aria-pressed', 'false')

    await user.click(topic(/Su \/ Tesisat/))
    await fillAndSubmit(user)

    expect(client.decide).toHaveBeenCalledWith({
      title: 'Lavabo akıtıyor',
      description: 'B blok ikinci kattaki ortak lavabo akıtıyor, su koridora yayılıyor.',
      location: 'B Blok, 2. kat',
    })
  })

  it('örnek metin alanları doldurur ve sayaçları gösterir', async () => {
    const { user } = await renderReady()

    await user.click(screen.getByRole('button', { name: 'Koridor lambası' }))

    expect(titleField()).toHaveValue('Koridor lambası yanmıyor')
    expect(locationField()).toHaveValue('A Blok, 3. kat koridor')
    expect(titleField().closest('label')).toHaveTextContent('24/120')
    expect(locationField().closest('label')).toHaveTextContent('22/120')
    expect(descriptionField().closest('label')).toHaveTextContent('/1000')
  })

  it('geçersiz girdide hata gösterir ve istek GÖNDERMEZ', async () => {
    const { user, client } = await renderReady()

    await user.type(titleField(), 'ab')
    await user.click(submitButton())

    expect(screen.getByText('Başlık en az 3 karakter olmalı.')).toBeInTheDocument()
    expect(client.decide).not.toHaveBeenCalled()
    expect(client.openSession).not.toHaveBeenCalled()
  })

  it('geçerli girdi kırpılarak gönderilir', async () => {
    const { user, client } = await renderReady()

    await user.type(titleField(), '  Priz yanıyor  ')
    await user.type(descriptionField(), '  Prizden duman çıktı, lütfen bakın.  ')
    await user.type(locationField(), '  C Blok  ')
    await user.click(submitButton())

    expect(client.decide).toHaveBeenCalledWith({
      title: 'Priz yanıyor',
      description: 'Prizden duman çıktı, lütfen bakın.',
      location: 'C Blok',
    })
  })

  it('çift tıklama tek istek gönderir', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => (release = resolve))
    const client = fakeDemoClient({
      decide: vi.fn(async () => {
        await gate
        return makeResult()
      }),
    })
    const { user } = await renderReady(client)
    await user.click(screen.getByRole('button', { name: 'Lavabo akıtıyor' }))

    await user.dblClick(submitButton())

    expect(client.decide).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Gönderiliyor…' })).toBeDisabled()
    release()
    await receipt()
    expect(client.decide).toHaveBeenCalledTimes(1)
  })
})

describe('DemoPage: talep fişi', () => {
  it('Jev kararı: numara, kategori, öncelik, ekip ve "Yapay zekâ" rozeti; teknik ayrıntılar katlıdır', async () => {
    const { user } = await renderReady()

    await fillAndSubmit(user)

    const card = await receipt()
    expect(within(card).getByRole('heading', { name: 'Talebin alındı ve ilgili ekibe yönlendirildi' })).toBeVisible()
    expect(card).toHaveTextContent('TA-0007')
    expect(card).toHaveTextContent('Yapay zekâ ön değerlendirmesi · Jev')
    expect(card).toHaveTextContent('Su/Tesisat')
    expect(card).toHaveTextContent('Yüksek')
    expect(card).toHaveTextContent('Su/Tesisat Ekibi')
    expect(card).toHaveTextContent('Atandı')
    expect(card).toHaveTextContent('Ekip şu bilgileri isteyebilir: İletişim bilgisi eksik.')
    expect(card).toHaveTextContent('Bildirdiğin sorun')
    expect(card).toHaveTextContent('gerçek bir bakım ekibine iletilmez')
    expect(screen.queryByRole('form', { name: 'Talep formu' })).toBeNull()

    const tech = screen.getByTestId('technical-details').closest('details')!
    expect(tech).not.toHaveAttribute('open')
    expect(tech).toHaveTextContent('Gerçek Jev (jev-1.13.0)')
    expect(tech).toHaveTextContent('uygulandı (talep durumu: Atandı)')
    expect(tech).toHaveTextContent('392')
    expect(tech).toHaveTextContent('0,000016464 USD')
    expect(tech).toHaveTextContent("Jev'in bildirdiği kullanımdan hesaplandı")
    const timings = within(screen.getByTestId('timings'))
    expect(timings.getByText('Sunucu uyanma')).toBeInTheDocument()
    expect(timings.getByText('Uçtan uca bekleme')).toBeInTheDocument()
    expect(timings.getByText('Jev çağrısı')).toBeInTheDocument()
    expect(timings.getByText('481 ms')).toBeInTheDocument()
    expect(tech).toHaveTextContent('benchmark sonucu değildir')
  })

  it('kural tabanlı karar: "yapay zekâ" denmez; ücret yok, Jev süresi yerine kural süresi', async () => {
    const decide = vi.fn().mockResolvedValue(ruleResult())
    const { user } = await renderReady(fakeDemoClient({ decide }))

    await fillAndSubmit(user)

    const card = await receipt()
    expect(card).toHaveTextContent('Kural tabanlı ön değerlendirme')
    expect(card).not.toHaveTextContent('Yapay zekâ ön değerlendirmesi')
    expect(card).not.toHaveTextContent('Gerçek Jev')
    expect(card).toHaveTextContent('ücretli çağrı yapılmadı')
    expect(card).toHaveTextContent('Su/Tesisat Ekibi')
    expect(card).toHaveTextContent("Jev'e bu talep için istek gönderilmedi")
    const timings = within(screen.getByTestId('timings'))
    expect(timings.getByText('Kural değerlendirmesi')).toBeInTheDocument()
    expect(timings.queryByText('Jev çağrısı')).toBeNull()
  })

  it('seçilen konu sistemin belirlediği kategoriyle karşılaştırılır (eşleşme ve fark)', async () => {
    const { user } = await renderReady()
    await user.click(topic(/Su \/ Tesisat/))
    await fillAndSubmit(user)
    expect(await receipt()).toHaveTextContent('Seçtiğin konu: Su/Tesisat · Sistemin metinden belirlediği: Su/Tesisat ✓')

    await user.click(screen.getByRole('button', { name: 'Yeni talep oluştur' }))
    await user.click(topic(/Elektrik/))
    await fillAndSubmit(user)
    expect(await receipt()).toHaveTextContent(
      'Seçtiğin konu: Elektrik · Sistemin metinden belirlediği: Su/Tesisat (farklı)',
    )
  })

  it('ekip atanamadıysa "insan incelemesine bırakıldı" ve nedenler listelenir', async () => {
    const result = makeResult({ team: null, ticket_status: 'needs_review' })
    result.decision!.review_required = true
    result.decision!.review_explanations = ['Metinde modele talimat veriyormuş gibi ifadeler algılandı.']
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    const card = await receipt()
    expect(within(card).getByRole('heading', { name: 'Talebin kaydedildi' })).toBeInTheDocument()
    expect(card).toHaveTextContent('İnsan incelemesine bırakıldı')
    expect(card).toHaveTextContent('İnceleme bekliyor')
    expect(card).toHaveTextContent('Bir görevli kontrol edecek:')
    expect(card).toHaveTextContent('modele talimat veriyormuş gibi')
  })

  it('mock sonuç "MOCK — gerçek model değil" rozetiyle gösterilir', async () => {
    const result = makeResult()
    result.decision!.is_mock = true
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    expect((await screen.findAllByText('MOCK — gerçek model değil')).length).toBeGreaterThan(0)
    expect(await receipt()).not.toHaveTextContent('Yapay zekâ ön değerlendirmesi')
  })

  it('yargı tablosu Jev güveni ile türetilmiş marjı ayrı etiketler', async () => {
    const { user } = await renderReady()
    await fillAndSubmit(user)

    const card = await receipt()
    await user.click(within(card).getByText(/Teknik ayrıntılar/))
    await user.click(within(card).getByText(/Soru bazında yargılar/))

    expect(card).toHaveTextContent('0,88 (Jev güveni)')
    expect(card).toHaveTextContent('türetilmiş marj; Jev güveni değil')
  })

  it('kullanım bildirilmediyse ücret "bilinmiyor", token "bildirilmedi" (sıfır değil)', async () => {
    const result = makeResult()
    result.usage = { ...result.usage!, input_tokens: null, output_tokens: null, cost_usd: null, cost_basis: 'unknown' }
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    const card = await receipt()
    expect(card).toHaveTextContent('bilinmiyor')
    expect(card).toHaveTextContent('bütçede en kötü bedelle sayılır')
    expect(card).toHaveTextContent('bildirilmedi')
    expect(card).not.toHaveTextContent('0,0000 USD')
  })

  it('belirsiz sonuç açıkça söylenir; karar uydurulmaz, yeniden gönder/sorgula yoktur', async () => {
    const result = makeResult({
      state: 'uncertain',
      message: 'Jev isteğinin sonucu bilinmiyor. OTOMATİK yeniden gönderilmedi.',
      team: null,
      decision: null,
      usage: null,
    })
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    const card = await receipt()
    expect(within(card).getByRole('heading', { name: 'Talebin kaydedildi' })).toBeInTheDocument()
    expect(card).toHaveTextContent('OTOMATİK yeniden gönderilmedi')
    expect(within(card).queryByRole('button', { name: /yeniden gönder/ })).toBeNull()
    expect(within(card).queryByRole('button', { name: 'Sonucu sorgula' })).toBeNull()
    expect(card).not.toHaveTextContent('Su/Tesisat Ekibi')
  })

  it('bekleyen talepte: sorgulama yalnızca okur', async () => {
    const pending = makeResult({
      state: 'pending',
      message: 'Kaydedildi; karar henüz çalışmadı.',
      decision: null,
      usage: null,
    })
    const decide = vi.fn().mockResolvedValueOnce(pending)
    const getDecision = vi.fn().mockResolvedValue(makeResult())
    const { user, client } = await renderReady(fakeDemoClient({ decide, getDecision }))
    await fillAndSubmit(user)
    const card = await receipt()
    expect(card).toHaveTextContent('Kaydedildi; karar henüz çalışmadı.')

    await user.click(within(card).getByRole('button', { name: 'Sonucu sorgula' }))

    expect(getDecision).toHaveBeenCalledWith('ticket-1')
    expect(decide).toHaveBeenCalledTimes(1) // sorgulama yeni çağrı başlatmadı
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Talebin alındı ve ilgili ekibe yönlendirildi' })).toBeInTheDocument(),
    )
    expect(client.openSession).toHaveBeenCalledTimes(1)
  })

  it('bekleyen talepte yeniden gönderme aynı metni tekrar yollar', async () => {
    const pending = makeResult({ state: 'pending', decision: null, usage: null })
    const decide = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(makeResult())
    const { user } = await renderReady(fakeDemoClient({ decide }))
    await fillAndSubmit(user)
    const card = await receipt()

    await user.click(within(card).getByRole('button', { name: 'Aynı talebi yeniden gönder' }))

    await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
    expect(decide.mock.calls[1][0]).toEqual(decide.mock.calls[0][0])
  })

  it('"Yeni talep oluştur" boş forma döner; sunucuya istek göndermez', async () => {
    const { user, client } = await renderReady()
    await user.click(topic(/Su \/ Tesisat/))
    await fillAndSubmit(user)
    await receipt()

    await user.click(screen.getByRole('button', { name: 'Yeni talep oluştur' }))

    expect(screen.getByRole('form', { name: 'Talep formu' })).toBeInTheDocument()
    expect(titleField()).toHaveValue('')
    expect(topic(/Su \/ Tesisat/)).toHaveAttribute('aria-pressed', 'false')
    expect(client.decide).toHaveBeenCalledTimes(1)
  })

  it('sunucu hata mesajı (429 vb.) olduğu gibi gösterilir; fiş uydurulmaz', async () => {
    const decide = vi.fn().mockRejectedValue(new ApiError(429, 'demo_capacity', 'Demo bugünkü kapasitesine ulaştı.'))
    const { user } = await renderReady(fakeDemoClient({ decide }))

    await fillAndSubmit(user)

    expect(await screen.findByText('Demo bugünkü kapasitesine ulaştı.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Talep fişi' })).toBeNull()
  })

  it('"Taleplerim" motordan bağımsız durum adıyla listelenir ve "Göster" yalnızca okur', async () => {
    storeDemoToken('var')
    const listDecisions = vi.fn().mockResolvedValue([makeSummary({ title: 'Eski talep', ticket_id: 'eski-1' })])
    const getDecision = vi.fn().mockResolvedValue(ruleResult({ ticket_id: 'eski-1', title: 'Eski talep' }))
    const { user, client } = await renderReady(fakeDemoClient({ listDecisions, getDecision }))

    const history = await screen.findByRole('region', { name: 'Taleplerim' })
    expect(history).toHaveTextContent('TA-0007')
    expect(history).toHaveTextContent('Eski talep')
    expect(history).toHaveTextContent('Değerlendirildi')
    expect(history).not.toHaveTextContent('Jev kararı üretildi')
    await user.click(within(history).getByRole('button', { name: 'Göster' }))

    expect(getDecision).toHaveBeenCalledWith('eski-1')
    expect(client.decide).not.toHaveBeenCalled()
    expect(await receipt()).toHaveTextContent('Eski talep')
  })
})

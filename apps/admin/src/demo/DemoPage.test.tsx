import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fakeDemoClient, makeResult, makeStatus, makeSummary } from '../demo-fixtures'
import { ApiError } from '../lib/api'
import { storeDemoToken, type DemoClient } from '../lib/demo-api'
import { vocab } from '../test-utils'
import DemoPage from './DemoPage'

beforeEach(() => storeDemoToken(null))

async function renderReady(client: DemoClient = fakeDemoClient()) {
  const user = userEvent.setup()
  render(<DemoPage client={client} vocab={vocab} />)
  await screen.findByTestId('wake-summary')
  return { user, client }
}

const submitButton = () => screen.getByRole('button', { name: /Gerçek Jev ile karar üret|Jev değerlendiriyor/ })

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Lavabo akıtıyor' }))
  await user.click(submitButton())
}

describe('DemoPage: hazırlık ve açıklama', () => {
  it('sunucu hazır olunca uyanma süresini (model süresinden ayrı) ve veri uyarısını gösterir', async () => {
    await renderReady(fakeDemoClient({ status: vi.fn().mockResolvedValue(makeStatus({ database_ms: 900 })) }))

    const summary = screen.getByTestId('wake-summary')
    expect(summary).toHaveTextContent('İlk istekten hazır olana kadar geçen süre')
    expect(summary).toHaveTextContent('veritabanı kısmı')
    expect(summary).toHaveTextContent('Jev çağrı süresi değildir')
    const notice = screen.getByText(/Bilmen gerekenler/).closest('div')!
    expect(notice).toHaveTextContent('Jev API sağlayıcısına gönderilir')
    expect(notice).toHaveTextContent('72 saat sonra otomatik silinir')
    expect(notice).toHaveTextContent('112')
  })

  it('sunucu hazır olana dek gönderme düğmesi kapalı; hazırlık isteği model çağırmaz', async () => {
    const client = fakeDemoClient({ status: vi.fn(() => new Promise(() => {})) })
    render(<DemoPage client={client} vocab={vocab} />)

    expect(await screen.findByText(/Sunucu hazırlanıyor/)).toHaveTextContent('model çağrısı yapmaz')
    expect(submitButton()).toBeDisabled()
    expect(screen.getByText('Sunucu hazır olunca açılır.')).toBeInTheDocument()
    expect(client.decide).not.toHaveBeenCalled()
  })

  it('demo kullanılamıyorsa nedeni gösterilir ve gönderme kapalıdır', async () => {
    const client = fakeDemoClient({
      status: vi.fn().mockResolvedValue(makeStatus({ enabled: false, reason: 'budget_exhausted' })),
    })
    await renderReady(client)

    expect(screen.getByRole('alert')).toHaveTextContent('bütçe doldu')
    expect(submitButton()).toBeDisabled()
    expect(client.decide).not.toHaveBeenCalled()
  })

  it('MOCK kurulumda sonuçlar açıkça "gerçek ölçüm değil" diye işaretlenir', async () => {
    await renderReady(
      fakeDemoClient({
        status: vi.fn().mockResolvedValue(makeStatus({ is_mock: true, provider: 'mock-jev' })),
      }),
    )

    expect(screen.getByText(/gerçek ölçüm değildir/)).toBeInTheDocument()
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
  it('hazır örnek alanları doldurur ve sayaçları gösterir', async () => {
    const { user } = await renderReady()

    await user.click(screen.getByRole('button', { name: 'Koridor lambası' }))

    expect(screen.getByLabelText(/^Başlık/)).toHaveValue('Koridor lambası yanmıyor')
    expect(screen.getByLabelText(/^Konum/)).toHaveValue('A Blok, 3. kat koridor')
    // Her alanın karakter sayacı vardır: başlık 24/120, açıklama .../1000, konum 22/120.
    expect(screen.getByLabelText(/^Başlık/).closest('label')).toHaveTextContent('24/120')
    expect(screen.getByLabelText(/^Konum/).closest('label')).toHaveTextContent('22/120')
    expect(screen.getByLabelText(/^Açıklama/).closest('label')).toHaveTextContent('/1000')
  })

  it('geçersiz girdide hata gösterir ve istek GÖNDERMEZ', async () => {
    const { user, client } = await renderReady()

    await user.type(screen.getByLabelText(/^Başlık/), 'ab')
    await user.click(submitButton())

    expect(screen.getByText('Başlık en az 3 karakter olmalı.')).toBeInTheDocument()
    expect(client.decide).not.toHaveBeenCalled()
    expect(client.openSession).not.toHaveBeenCalled()
  })

  it('geçerli girdi kırpılarak gönderilir', async () => {
    const { user, client } = await renderReady()

    await user.type(screen.getByLabelText(/^Başlık/), '  Priz yanıyor  ')
    await user.type(screen.getByLabelText(/^Açıklama/), '  Prizden duman çıktı, lütfen bakın.  ')
    await user.type(screen.getByLabelText(/^Konum/), '  C Blok  ')
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
    expect(screen.getByRole('button', { name: /Jev değerlendiriyor/ })).toBeDisabled()
    release()
    await screen.findByRole('region', { name: 'Sonuç' })
    expect(client.decide).toHaveBeenCalledTimes(1)
  })
})

describe('DemoPage: sonuç', () => {
  it('kategori, öncelik, uygulanma durumu, gerçek token ve ücret, ayrı süreler gösterilir', async () => {
    const { user } = await renderReady()

    await fillAndSubmit(user)

    const panel = await screen.findByRole('region', { name: 'Sonuç' })
    expect(within(panel).getByRole('heading', { name: /Sonuç — TA-0007/ })).toBeInTheDocument()
    expect(panel).toHaveTextContent('Gerçek Jev (jev-1.13.0)')
    expect(panel).toHaveTextContent('Su/Tesisat')
    expect(panel).toHaveTextContent('Yüksek')
    expect(panel).toHaveTextContent('uygulandı (talep durumu: Atandı)')
    expect(panel).toHaveTextContent('İletişim bilgisi eksik')
    expect(panel).toHaveTextContent('gerekmiyor')
    expect(panel).toHaveTextContent('392')
    expect(panel).toHaveTextContent('65')
    expect(panel).toHaveTextContent('çıktı tokenları ücretsiz')
    expect(panel).toHaveTextContent('0,000016464 USD')
    expect(panel).toHaveTextContent("Jev'in bildirdiği kullanımdan hesaplandı")
    const timings = within(screen.getByTestId('timings'))
    expect(timings.getByText('Sunucu uyanma')).toBeInTheDocument()
    expect(timings.getByText('Uçtan uca bekleme')).toBeInTheDocument()
    expect(timings.getByText('Jev çağrısı')).toBeInTheDocument()
    expect(timings.getByText('481 ms')).toBeInTheDocument()
    expect(panel).toHaveTextContent('benchmark sonucu değildir')
    expect(panel).toHaveTextContent('doğruluk oranı çıkarılmaz')
  })

  it('yargı tablosu Jev güveni ile türetilmiş marjı ayrı etiketler', async () => {
    const { user } = await renderReady()
    await fillAndSubmit(user)

    const panel = await screen.findByRole('region', { name: 'Sonuç' })
    await user.click(within(panel).getByText(/Soru bazında yargılar/))

    expect(panel).toHaveTextContent('0,88 (Jev güveni)')
    expect(panel).toHaveTextContent('türetilmiş marj; Jev güveni değil')
    expect(panel).toHaveTextContent('Konum')
  })

  it('kullanım bildirilmediyse ücret "bilinmiyor", token "bildirilmedi" (sıfır değil)', async () => {
    const result = makeResult()
    result.usage = {
      ...result.usage!,
      input_tokens: null,
      output_tokens: null,
      cost_usd: null,
      cost_basis: 'unknown',
    }
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    const panel = await screen.findByRole('region', { name: 'Sonuç' })
    expect(panel).toHaveTextContent('bilinmiyor')
    expect(panel).toHaveTextContent('bütçede en kötü bedelle sayılır')
    expect(panel).toHaveTextContent('bildirilmedi')
    expect(panel).not.toHaveTextContent('0,0000 USD')
  })

  it('inceleme gereken kararda nedenler listelenir', async () => {
    const result = makeResult()
    result.decision!.review_required = true
    result.decision!.review_explanations = ['Metinde modele talimat veriyormuş gibi ifadeler algılandı.']
    result.ticket_status = 'needs_review'
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    const panel = await screen.findByRole('region', { name: 'Sonuç' })
    expect(panel).toHaveTextContent('gerekiyor')
    expect(panel).toHaveTextContent('modele talimat veriyormuş gibi')
    expect(panel).toHaveTextContent('talep durumu: İnceleme bekliyor')
  })

  it('mock sonuç "MOCK — gerçek model değil" rozetiyle gösterilir', async () => {
    const result = makeResult()
    result.decision!.is_mock = true
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    expect(await screen.findByText('MOCK — gerçek model değil')).toBeInTheDocument()
    expect(screen.queryByText(/Gerçek Jev \(/)).not.toBeInTheDocument()
  })

  it('belirsiz sonuç açıkça söylenir; yeniden gönder/sorgula düğmeleri yoktur', async () => {
    const result = makeResult({
      state: 'uncertain',
      message: 'Jev isteğinin sonucu bilinmiyor. OTOMATİK yeniden gönderilmedi.',
      decision: null,
      usage: null,
    })
    const { user } = await renderReady(fakeDemoClient({ decide: vi.fn().mockResolvedValue(result) }))

    await fillAndSubmit(user)

    const panel = await screen.findByRole('region', { name: 'Sonuç' })
    expect(panel).toHaveTextContent('Sonuç belirsiz')
    expect(panel).toHaveTextContent('OTOMATİK yeniden gönderilmedi')
    expect(panel).toHaveTextContent("Jev'e bu talep için istek gönderilmedi")
    expect(within(panel).queryByRole('button', { name: /yeniden gönder/ })).toBeNull()
    expect(within(panel).queryByRole('button', { name: 'Sonucu sorgula' })).toBeNull()
    expect(panel).not.toHaveTextContent('Su/Tesisat') // uydurma karar yok
  })

  it('bekleyen talepte: sorgulama yalnızca okur, yeniden gönderme aynı metni yollar', async () => {
    const pending = makeResult({
      state: 'pending',
      message: 'Kaydedildi; karar henüz çalışmadı.',
      decision: null,
      usage: null,
    })
    const decide = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(makeResult())
    const getDecision = vi.fn().mockResolvedValue(makeResult({ state: 'running', decision: null, usage: null }))
    const { user, client } = await renderReady(fakeDemoClient({ decide, getDecision }))
    await fillAndSubmit(user)
    const panel = await screen.findByRole('region', { name: 'Sonuç' })

    await user.click(within(panel).getByRole('button', { name: 'Sonucu sorgula' }))

    expect(getDecision).toHaveBeenCalledWith('ticket-1')
    expect(decide).toHaveBeenCalledTimes(1) // sorgulama ücretli çağrı başlatmadı
    await waitFor(() => expect(screen.getByRole('region', { name: 'Sonuç' })).toHaveTextContent('Karar üretiliyor'))
    expect(client.openSession).toHaveBeenCalledTimes(1)
  })

  it('bekleyen talepte yeniden gönderme aynı metni tekrar yollar', async () => {
    const pending = makeResult({ state: 'pending', decision: null, usage: null })
    const decide = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(makeResult())
    const { user } = await renderReady(fakeDemoClient({ decide }))
    await fillAndSubmit(user)
    const panel = await screen.findByRole('region', { name: 'Sonuç' })

    await user.click(within(panel).getByRole('button', { name: 'Aynı talebi yeniden gönder' }))

    await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
    expect(decide.mock.calls[1][0]).toEqual({
      title: 'Lavabo akıtıyor',
      description: 'B blok ikinci kattaki ortak lavabo akıtıyor, su koridora yayılıyor.',
      location: 'B Blok, 2. kat',
    })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Sonuç' })).toHaveTextContent('Jev kararı üretildi'))
  })

  it('sunucu hata mesajı (429 vb.) olduğu gibi gösterilir', async () => {
    const decide = vi.fn().mockRejectedValue(new ApiError(429, 'demo_capacity', 'Demo bugünkü kapasitesine ulaştı.'))
    const { user } = await renderReady(fakeDemoClient({ decide }))

    await fillAndSubmit(user)

    expect(await screen.findByText('Demo bugünkü kapasitesine ulaştı.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Sonuç' })).toBeNull()
  })

  it('önceki denemeler listelenir ve "Göster" yalnızca okur', async () => {
    storeDemoToken('var')
    const listDecisions = vi.fn().mockResolvedValue([makeSummary({ title: 'Eski talep', ticket_id: 'eski-1' })])
    const getDecision = vi.fn().mockResolvedValue(makeResult({ ticket_id: 'eski-1', title: 'Eski talep' }))
    const { user, client } = await renderReady(fakeDemoClient({ listDecisions, getDecision }))

    const history = await screen.findByRole('region', { name: 'Önceki denemelerim' })
    expect(history).toHaveTextContent('TA-0007 — Eski talep')
    await user.click(within(history).getByRole('button', { name: 'Göster' }))

    expect(getDecision).toHaveBeenCalledWith('eski-1')
    expect(client.decide).not.toHaveBeenCalled()
    expect(await screen.findByRole('region', { name: 'Sonuç' })).toHaveTextContent('Eski talep')
  })
})

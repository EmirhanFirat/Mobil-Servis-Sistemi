import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { makeDetail, makeSample } from '../experiment-fixtures'
import type { ExperimentDetail } from '../lib/experiment-types'
import { vocab } from '../test-utils'
import ShareCard from './ShareCard'

/** Satırlar ayrı <text> öğeleridir; okunan metin için boşlukla birleştirilir. */
function text(detail: ExperimentDetail, withSample = true): string {
  render(<ShareCard detail={detail} example={withSample ? makeSample() : null} vocab={vocab} />)
  return Array.from(screen.getByTestId('share-card').querySelectorAll('text'))
    .map((node) => node.textContent ?? '')
    .join(' ')
}

describe('ShareCard', () => {
  it('üç modelin temel ölçümlerini ve veri kaynağını gösterir', () => {
    const content = text(makeDetail())

    expect(content).toContain('Jev, LLM ve hibrit: Türkçe servis taleplerinde karar karşılaştırması')
    for (const name of ['Jev', 'LLM', 'Hibrit']) expect(content).toContain(name)
    expect(content).toContain('Kategori doğruluğu')
    expect(content).toContain('%100,0 (5/5)')
    expect(content).toContain('%80,0 (4/5)')
    expect(content).toContain('Toplam bilinen model ücreti (ölçülen)')
    expect(content).toContain('Tamamlanan talep başına ücret (ölçülen)') // etiket kesilmez
    expect(content).not.toContain('…')
    expect(content).toContain('0,01471 USD')
    expect(content).toContain('1.569 ms')
    expect(content).toContain('902 (tamamı ücretsiz çıktı)')
  })

  it('mevcut deney "5 sentetik geliştirme örneği — bağlantı denemesi" olarak işaretli', () => {
    expect(text(makeDetail())).toContain('5 sentetik geliştirme örneği — bağlantı denemesi')
  })

  it('altbilgide kaynak, tarih, model sürümleri ve eski hibrit sürümü açıkça yazılır', () => {
    const content = text(makeDetail())

    expect(content).toContain('Veri kaynağı: sentetik veri seti v1')
    expect(content).toContain('02.10.2026')
    expect(content).toContain('jev-1.13.0')
    expect(content).toContain('claude-haiku-4-5-20251001')
    expect(content).toContain('Hibrit v1 — kayıtta sürüm yok, eski yönlendirme')
    expect(content).toContain('genelleme veya tasarruf sonucu çıkarılamaz')
  })

  it('1.000 talebe tahmin satırı görsele girmez (ölçülen ile tahmin karıştırılmaz)', () => {
    const content = text(makeDetail())

    expect(content).not.toContain('1.000 talebe')
    expect(content).not.toContain('(tahmin)')
  })

  it('ücret ve gecikme AYRI grafiklerdir; her birinin birimi kendi başlığındadır', () => {
    text(makeDetail())

    const cost = screen.getByRole('img', { name: 'Tamamlanan talep başına ölçülen ücret' })
    const latency = screen.getByRole('img', { name: 'Uçtan uca karar süresi' })

    expect(cost).not.toBe(latency)
    expect(cost.textContent).toContain('USD')
    expect(cost.textContent).not.toContain('milisaniye')
    expect(latency.textContent).toContain('milisaniye')
    expect(latency.textContent).not.toContain('USD')
    expect(cost.textContent).toContain('0,0000386652')
    expect(latency.textContent).toContain('p50')
    expect(latency.textContent).toContain('p95')
  })

  it('bilinmeyen ücret grafikte "bilinmiyor" yazılır, sıfır çubuk çizilmez', () => {
    const detail = makeDetail()
    detail.strategies[0] = {
      ...detail.strategies[0],
      cost: {
        known_usd: '0.0001',
        calls_with_unknown_cost: 1,
        total_usd: null,
        per_completed_usd: null,
        estimate_per_1000_usd: null,
      },
    }
    text(detail)

    const cost = screen.getByRole('img', { name: 'Tamamlanan talep başına ölçülen ücret' })

    expect(cost.textContent).toContain('bilinmiyor')
    expect(cost.querySelectorAll('rect')).toHaveLength(2) // yalnızca bilinen iki strateji
  })

  it('örnek talep: tam metin, beklenen etiket, üç tahmin ve tartışmalı etiket işareti', () => {
    const content = text(makeDetail())

    expect(content).toContain('Örnek talep karşılaştırması · s023')
    expect(content).toContain('Asansör kapısı kapanmıyor, kata gelince açılmıyor.')
    expect(content).toContain('Beklenen etiket: Diğer · Normal')
    expect(content).toContain('Tartışmalı etiket (ikinci değerlendirme bekliyor)')
    expect(content).toContain('Öncelik: Yüksek (yanlış)') // metinle de belirtilir, yalnızca renkle değil
    expect(content).toContain("LLM'e giden: İletişim bilgisi eksik mi")
  })

  it("LLM'e giden sorular sütuna sarılır; ikinci satır birincinin ALTINA yazılır (üst üste binmez)", () => {
    render(<ShareCard detail={makeDetail()} example={makeSample()} vocab={vocab} />)
    const texts = Array.from(screen.getByTestId('share-card').querySelectorAll('text'))
    const first = texts.find((node) => node.textContent?.startsWith("LLM'e giden:"))!
    const second = texts.find((node) => node.textContent === 'eksik mi')!

    expect(first.textContent).toBe("LLM'e giden: İletişim bilgisi")
    expect(first.getAttribute('x')).toBe(second.getAttribute('x'))
    expect(Number(second.getAttribute('y')) - Number(first.getAttribute('y'))).toBeCloseTo(19.6, 1)
  })

  it('örnek seçilmediyse bunu söyler', () => {
    expect(text(makeDetail(), false)).toContain('Örnek talep seçilmedi.')
  })

  it('PNG için bağımsızdır: boyut ve xmlns var, CSS sınıfı ve harici kaynak yok', () => {
    text(makeDetail())
    const svg = screen.getByTestId('share-card')

    expect(svg.getAttribute('width')).toBe('1200')
    expect(Number(svg.getAttribute('height'))).toBeGreaterThan(600)
    expect(svg.getAttribute('xmlns')).toBe('http://www.w3.org/2000/svg')
    expect(svg.outerHTML).not.toMatch(/\sclass=/)
    expect(svg.outerHTML).not.toMatch(/href=|url\(|<image|<foreignObject/)
  })

  it('arka plan sabit beyazdır (tema bağımsız)', () => {
    text(makeDetail())

    expect(screen.getByTestId('share-card').querySelector('rect')?.getAttribute('fill')).toBe('#ffffff')
  })
})

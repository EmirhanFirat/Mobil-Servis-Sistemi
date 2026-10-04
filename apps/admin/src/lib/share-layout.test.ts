import { describe, expect, it } from 'vitest'

import { makeDetail, makeRun, makeSample } from '../experiment-fixtures'
import { SHARE_KEYS, SHARE_WIDTH } from './chart-data'
import { computeShareLayout, escalationLines, rowHeight } from './share-layout'

describe('computeShareLayout', () => {
  const detail = makeDetail()

  it('yalnızca paylaşım ölçütlerini içerir; tahmini ölçekleme satırı yok', () => {
    const keys = computeShareLayout(detail, null).rows.map((r) => r.row.key)

    expect(keys).toEqual(SHARE_KEYS)
    expect(keys).not.toContain('cost_estimate_1000')
  })

  it('aynı veriyle aynı yerleşim (belirleyici)', () => {
    expect(computeShareLayout(detail, makeSample())).toEqual(computeShareLayout(detail, makeSample()))
  })

  it('örnek talep eklenince görsel uzar; satırlar üst üste binmez', () => {
    const without = computeShareLayout(detail, null)
    const withSample = computeShareLayout(detail, makeSample())

    expect(withSample.height).toBeGreaterThan(without.height)
    for (let i = 1; i < withSample.rows.length; i++) {
      const previous = withSample.rows[i - 1]
      expect(withSample.rows[i].top).toBe(previous.top + previous.height)
    }
    expect(withSample.chartTop).toBeGreaterThan(withSample.rows.at(-1)!.top)
    expect(withSample.exampleTop).toBeGreaterThan(withSample.chartTop)
    expect(withSample.footerTop).toBeGreaterThan(withSample.exampleTop)
  })

  it('küçük deney bağlantı denemesi olarak (uyarı renginde) işaretlenir', () => {
    const layout = computeShareLayout(detail, null)

    expect(layout.scope).toBe('5 sentetik geliştirme örneği — bağlantı denemesi')
    expect(layout.warn).toBe(true)
    expect(layout.pillWidth).toBeLessThanOrEqual(SHARE_WIDTH - 80)
  })

  it('altbilgi veri kaynağını, örnek sayısını, tarihi, sürümleri ve uyarıları taşır', () => {
    const footer = computeShareLayout(detail, null).footer.join(' ')

    expect(footer).toContain('Veri kaynağı: sentetik veri seti v1')
    expect(footer).toContain('etiketler tek kişiyce yazıldı, gözden geçirilmedi')
    expect(footer).toContain('5 sentetik geliştirme örneği — bağlantı denemesi')
    expect(footer).toContain('02.10.2026')
    expect(footer).toContain('Kaynak commit: 09584e9')
    expect(footer).toContain('Jev = jev-1.13.0')
    expect(footer).toContain('claude-haiku-4-5-20251001')
    expect(footer).toContain('Hibrit v1 — kayıtta sürüm yok, eski yönlendirme')
    expect(footer).toContain('Küçük örneklem')
    expect(footer).toContain('Tartışmalı etiketli örnek')
    expect(footer).toContain('tokenizer')
  })

  it('büyük ve uyarısız deneyde küçük örneklem uyarısı yazılmaz', () => {
    const big = makeDetail({
      run: makeRun({ scope_label: '36 sentetik geliştirme + doğrulama örneği' }),
      warnings: [],
    })

    const layout = computeShareLayout(big, null)

    expect(layout.warn).toBe(false)
    expect(layout.footer.join(' ')).not.toContain('Küçük örneklem')
  })

  it('hibrit içermeyen deneyde yönlendirme satırı yoktur', () => {
    const noHybrid = makeDetail({ run: makeRun({ hybrid_routing: null }) })

    expect(computeShareLayout(noHybrid, null).footer.join(' ')).not.toContain('Hibrit yönlendirme')
  })

  it('ölçüt etiketleri kısaltılmaz; uzun etiket iki satıra sarılır', () => {
    const rows = computeShareLayout(detail, null).rows
    const cost = rows.find((r) => r.row.key === 'cost_per_completed')!

    expect(cost.labelLines.join(' ')).toBe(cost.row.label)
    expect(cost.labelLines.join(' ')).not.toContain('…')
    for (const r of rows) expect(r.labelLines.join(' ')).toBe(r.row.label)
  })

  it('rowHeight: etiket veya hücre ikinci satıra sarılırsa satır yükselir', () => {
    expect(rowHeight(['tek'], [['a'], ['b']])).toBe(34)
    expect(rowHeight(['bir', 'iki'], [['a'], ['b']])).toBe(52) // yalnızca etiket sarıldı
    expect(rowHeight(['tek'], [['a'], ['b', 'c']])).toBe(52) // yalnızca hücre sarıldı
  })

  describe('escalationLines', () => {
    const hybrid = () => makeSample().strategies.find((s) => s.info.kind === 'hybrid')!

    it('yalnızca hibrit için ve "LLM\'e giden:" ile başlar', () => {
      const sample = makeSample()
      const jev = sample.strategies.find((s) => s.info.kind === 'jev_only')!

      expect(escalationLines(jev)).toEqual([])
      // 30 karakterlik sütuna sığmadığı için iki satıra bölünür (sağ kenardan taşmaz)
      expect(escalationLines(hybrid())).toEqual(["LLM'e giden: İletişim bilgisi", 'eksik mi'])
    })

    it('hiç soru gitmediyse "yok" yazar; çalışmayan/eksik kayıtta boş döner', () => {
      const none = { ...hybrid(), escalated_questions: [] }

      expect(escalationLines(none)).toEqual(["LLM'e giden: yok"])
      expect(escalationLines({ ...hybrid(), present: false })).toEqual([])
      expect(escalationLines({ ...hybrid(), failed: true })).toEqual([])
    })

    it('uzun soru listesi sütun genişliğine sarılır, en çok 3 satır', () => {
      const many = {
        ...hybrid(),
        escalated_questions: ['category', 'priority', 'missing_location', 'missing_detail', 'missing_contact'],
      }

      const lines = escalationLines(many)

      expect(lines.length).toBeGreaterThan(1)
      expect(lines.length).toBeLessThanOrEqual(3)
      for (const line of lines) expect(line.length).toBeLessThanOrEqual(30)
    })

    it('uzun soru listesi örnek kutusunu uzatır; kısa listeyle kutu varsayılan yükseklikte kalır', () => {
      const short = makeSample()
      const long = makeSample()
      short.sample.description = long.sample.description = 'kısa' // yükseklik soru sütunlarından gelsin
      const target = long.strategies.find((s) => s.info.kind === 'hybrid')!
      target.escalated_questions = ['category', 'priority', 'missing_location', 'missing_detail', 'missing_contact']

      const shortLayout = computeShareLayout(detail, short)
      const longLayout = computeShareLayout(detail, long)

      expect(longLayout.exampleHeight).toBeGreaterThan(shortLayout.exampleHeight)
      expect(longLayout.height).toBeGreaterThan(shortLayout.height)
    })
  })

  it('uzun açıklama sınırlı satıra kısaltılır', () => {
    const sample = makeSample()
    sample.sample.description = 'çok uzun açıklama '.repeat(80)

    const layout = computeShareLayout(detail, sample)

    expect(layout.textLines.length).toBeLessThanOrEqual(9)
    expect(layout.textLines.join(' ')).toContain('…')
  })
})

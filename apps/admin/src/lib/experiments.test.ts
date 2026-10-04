import { describe, expect, it } from 'vitest'

import { makeDetail, makeList, makeRun } from '../experiment-fixtures'
import type { ExperimentDetail, StrategyResult } from './experiment-types'
import {
  NA,
  UNKNOWN,
  buildCsv,
  buildMarkdown,
  comparisonRows,
  csvCell,
  decimalText,
  defaultExampleId,
  exportFileName,
  filterSamples,
  formatCount,
  formatMs,
  formatPercent,
  formatUsd,
  routingLabel,
  runOptionText,
  scopeLabel,
  statusText,
  strategyModelLine,
  strategyTitle,
} from './experiments'

function row(detail: ExperimentDetail, key: string): Record<string, string> {
  const found = comparisonRows(detail).find((item) => item.key === key)
  if (!found) throw new Error(`satır yok: ${key}`)
  return found.cells
}

function withStrategy(
  detail: ExperimentDetail,
  name: string,
  patch: (result: StrategyResult) => StrategyResult,
): ExperimentDetail {
  return { ...detail, strategies: detail.strategies.map((s) => (s.name === name ? patch(s) : s)) }
}

describe('biçimler', () => {
  it('ücret: çok küçük değerlerde hassasiyet korunur, gereksiz sıfırlar atılır', () => {
    expect(formatUsd('0.0000386652')).toBe('0,0000386652 USD')
    expect(formatUsd('0.000193326')).toBe('0,000193326 USD')
    expect(formatUsd('0.01471')).toBe('0,01471 USD')
    expect(formatUsd('2.942')).toBe('2,9420 USD')
    expect(formatUsd('0')).toBe('0,0000 USD')
    expect(decimalText('1234.5')).toBe('1.234,5000')
  })

  it('bilinmeyen ücret "bilinmiyor" yazılır, sıfır değil', () => {
    expect(formatUsd(null)).toBe(UNKNOWN)
    expect(formatUsd(undefined)).toBe(UNKNOWN)
    expect(formatUsd(null)).not.toContain('0')
  })

  it('yüzde ve oran; boş örneklemde tire', () => {
    expect(formatPercent({ successes: 4, n: 5, value: 0.8, wilson95: null })).toBe('%80,0 (4/5)')
    expect(formatPercent({ successes: 0, n: 0, value: null, wilson95: null })).toBe(NA)
  })

  it('süre ve sayı tr-TR; bilinmeyen süre sıfır değil', () => {
    expect(formatMs(1569.493)).toBe('1.569 ms')
    expect(formatMs(null)).toBe(UNKNOWN)
    expect(formatCount(9703)).toBe('9.703')
  })
})

describe('adlar ve sürümler', () => {
  it('strateji adı ve gerçek model sürümü', () => {
    const [jev, llm, hybrid] = makeDetail().strategies
    expect(strategyTitle(jev.info)).toBe('Jev')
    expect(strategyTitle(llm.info)).toBe('LLM')
    expect(strategyTitle(hybrid.info)).toBe('Hibrit')
    expect(strategyModelLine(jev.info)).toBe('jev-1.13.0')
    expect(strategyModelLine(hybrid.info)).toBe('jev-1.13.0 + claude-haiku-4-5-20251001')
  })

  it('mock strateji açıkça işaretlenir', () => {
    const jev = makeDetail().strategies[0].info
    expect(strategyTitle({ ...jev, is_mock: true })).toBe('Jev (MOCK)')
  })

  it('kayıtta sürüm alanı olmayan hibrit v1 "eski yönlendirme" diye etiketlenir', () => {
    const v1 = routingLabel(makeRun().hybrid_routing)
    expect(v1).toContain('Hibrit v1')
    expect(v1).toContain('kayıtta sürüm yok')
    expect(v1).toContain('eski yönlendirme')
    expect(routingLabel({ version: 'hibrit-yonlendirme-v2', recorded: true, description: '' })).toBe('Hibrit v2')
    expect(routingLabel(null)).toBe(NA)
  })

  it('durum metinleri', () => {
    expect(statusText('complete')).toBe('Tamamlandı')
    expect(statusText('partial')).toBe('Yarım kaldı')
    expect(statusText('missing_files')).toBe('Kayıtlar eksik')
    expect(statusText('corrupt')).toBe('Bozuk kayıt')
  })

  it('mevcut 5 örneklik deney "5 sentetik geliştirme örneği — bağlantı denemesi" olarak işaretli', () => {
    expect(scopeLabel(makeRun())).toBe('5 sentetik geliştirme örneği — bağlantı denemesi')
  })

  it('seçici satırı tarih, örnek kapsamı, stratejiler ve durumu içerir', () => {
    const text = runOptionText(makeRun())
    expect(text).toContain('02.10.2026')
    expect(text).toContain('5 sentetik geliştirme örneği — bağlantı denemesi')
    expect(text).toContain('Jev + LLM + Hibrit')
    expect(text).toContain('Tamamlandı')
  })

  it('dosya adı deney kimliğini taşır', () => {
    expect(exportFileName(makeRun(), 'png')).toBe(`model-karsilastirma-${makeRun().id}.png`)
  })
})

describe('karşılaştırma satırları', () => {
  const detail = makeDetail()

  it('doğruluk, öncelik ve kaçırılan yüksek öncelikli talepler', () => {
    expect(row(detail, 'category_accuracy').jev_only).toBe('%100,0 (5/5)')
    expect(row(detail, 'category_macro_f1').jev_only).toBe('1,00')
    expect(row(detail, 'priority_accuracy').llm_only).toBe('%80,0 (4/5)')
    expect(row(detail, 'high_priority_missed').hybrid).toBe('0 / 1')
  })

  it('inceleme ve otomatik karar oranı ayrı satırlar', () => {
    expect(row(detail, 'review_rate').hybrid).toBe('%0,0 (0/5)')
    expect(row(detail, 'automated_rate').hybrid).toBe('%100,0 (5/5)')
  })

  it('p50/p95 gecikme uçtan uca', () => {
    expect(row(detail, 'latency_p50').jev_only).toBe('315 ms')
    expect(row(detail, 'latency_p95').llm_only).toBe('2.266 ms')
  })

  it('ölçülen toplam ile 1.000 talebe tahmin AYRI satırlardır ve tahmin açıkça etiketlidir', () => {
    const rows = comparisonRows(detail)
    const measured = rows.find((r) => r.key === 'cost_known')
    const estimate = rows.find((r) => r.key === 'cost_estimate_1000')
    expect(measured?.label).toContain('ölçülen')
    expect(estimate?.label).toContain('TAHMİN')
    expect(estimate?.note).toContain('ölçülen değil')
    expect(estimate?.cells.llm_only).toBe('2,9420 USD (tahmin)')
    expect(measured?.cells.llm_only).toBe('0,01471 USD')
  })

  it('token ve ücret ayrı satırlar; ücretsiz çıktı tokenı sıfır gösterilmez, ücretsiz diye işaretlenir', () => {
    expect(row(detail, 'input_tokens').jev_only).toBe('4.603')
    expect(row(detail, 'output_tokens').jev_only).toBe('902 (tamamı ücretsiz çıktı)')
    expect(row(detail, 'output_tokens').llm_only).toBe('974')
    // Hibritte yalnızca Jev'in çıktısı ücretsiz.
    expect(row(detail, 'output_tokens').hybrid).toBe('1.138 (902 tanesi ücretsiz çıktı)')
  })

  it('hibritte sağlayıcı bazında token dağılımı; tek sağlayıcılı stratejide tire', () => {
    expect(row(detail, 'provider_split').hybrid).toBe(
      'Anthropic: 5.100 giriş / 236 çıkış · Jev: 4.603 giriş / 902 çıkış',
    )
    expect(row(detail, 'provider_split').jev_only).toBe(NA)
  })

  it('çağrı, retry, hata ve başarısız karar', () => {
    expect(row(detail, 'calls').hybrid).toBe('10 / 0 / 0')
    expect(row(detail, 'failed_decisions').jev_only).toBe('0')
  })

  it("hibritte LLM'e geçiş oranı ve tetikleyen sorular; diğer stratejilerde geçerli değil", () => {
    expect(row(detail, 'escalation_rate').hybrid).toBe('%100,0 (5/5)')
    expect(row(detail, 'escalation_rate').jev_only).toBe(NA)
    expect(row(detail, 'escalation_questions').hybrid).toBe('İletişim bilgisi eksik mi? (5)')
    expect(row(detail, 'escalation_questions').llm_only).toBe(NA)
  })

  it("LLM'e hiç geçilmediyse bunu söyler", () => {
    const none = withStrategy(detail, 'hybrid', (s) => ({
      ...s,
      hybrid: s.hybrid && { ...s.hybrid, trigger_questions: {} },
    }))
    expect(row(none, 'escalation_questions').hybrid).toBe("LLM'e geçiş olmadı")
  })

  it('bilinmeyen ücretli çağrı: toplam "bilinen + bilinmeyen", talep başı ve tahmin "bilinmiyor" (sıfır değil)', () => {
    const unknown = withStrategy(detail, 'jev_only', (s) => ({
      ...s,
      cost: {
        known_usd: '0.000114',
        calls_with_unknown_cost: 2,
        total_usd: null,
        per_completed_usd: null,
        estimate_per_1000_usd: null,
      },
    }))
    expect(row(unknown, 'cost_known').jev_only).toBe('0,000114 USD bilinen + 2 çağrının ücreti bilinmiyor')
    expect(row(unknown, 'cost_per_completed').jev_only).toBe(UNKNOWN)
    expect(row(unknown, 'cost_estimate_1000').jev_only).toBe(UNKNOWN)
  })

  it('eksik metrik sıfır gösterilmez', () => {
    const missing = withStrategy(detail, 'llm_only', (s) => ({
      ...s,
      metrics: { ...s.metrics, latency_p50_ms: null, category_macro_f1: null },
    }))
    expect(row(missing, 'latency_p50').llm_only).toBe(UNKNOWN)
    expect(row(missing, 'category_macro_f1').llm_only).toBe(UNKNOWN)
  })

  it('bildirilmeyen girdi kullanımı açıkça yazılır', () => {
    const silent = withStrategy(detail, 'llm_only', (s) => ({
      ...s,
      usage: { ...s.usage, calls_without_usage: 2 },
    }))
    expect(row(silent, 'input_tokens').llm_only).toContain('2 çağrı bildirmedi')
  })
})

describe('dışa aktarma', () => {
  const detail = makeDetail()

  it('CSV: BOM, strateji başına bir satır, nokta ondalık, birimsiz ve tahmin sütunu açık adlı', () => {
    const csv = buildCsv(detail)
    const lines = csv.replace('﻿', '').trim().split('\r\n')

    expect(csv.startsWith('﻿')).toBe(true)
    expect(lines).toHaveLength(1 + 3)
    const header = lines[0].split(',')
    expect(header).toContain('tahmini_1000_talep_ucreti_usd_TAHMIN')
    const llm = lines[2].split(',')
    const at = (name: string) => llm[header.indexOf(name)]
    expect(at('strateji')).toBe('llm_only')
    expect(at('model')).toBe('claude-haiku-4-5-20251001')
    expect(at('olculen_toplam_ucret_usd')).toBe('0.01471')
    expect(at('talep_basi_ucret_usd')).toBe('0.002942')
    expect(at('tahmini_1000_talep_ucreti_usd_TAHMIN')).toBe('2.942')
    expect(at('girdi_token')).toBe('9840')
    expect(at('hibrit_llm_gecis_orani')).toBe('') // geçerli değil: boş, sıfır değil
  })

  it('CSV: hibrit satırı geçiş oranı ve sorularını taşır; v1 kayıtta yok diye yazılır', () => {
    const lines = buildCsv(detail).replace('﻿', '').trim().split('\r\n')
    const header = lines[0].split(',')
    const hybrid = lines[3].split(',')

    expect(hybrid[header.indexOf('hibrit_llm_gecis_orani')]).toBe('1')
    expect(hybrid[header.indexOf('hibrit_llm_gecis_sorulari')]).toBe('missing_contact:5')
    expect(lines[3]).toContain('hibrit-yonlendirme-v1 (kayıtta yok)')
  })

  it('CSV: bilinmeyen ücret boş bırakılır (sıfır değil)', () => {
    const unknown = withStrategy(detail, 'jev_only', (s) => ({
      ...s,
      cost: {
        known_usd: '0.000114',
        calls_with_unknown_cost: 2,
        total_usd: null,
        per_completed_usd: null,
        estimate_per_1000_usd: null,
      },
    }))
    const lines = buildCsv(unknown).replace('﻿', '').trim().split('\r\n')
    const header = lines[0].split(',')
    const jev = lines[1].split(',')

    expect(jev[header.indexOf('olculen_toplam_ucret_usd')]).toBe('')
    expect(jev[header.indexOf('talep_basi_ucret_usd')]).toBe('')
    expect(jev[header.indexOf('ucreti_bilinmeyen_cagri')]).toBe('2')
  })

  it('csvCell: virgül, tırnak ve satır sonu kaçışlanır; boş değer boş hücre', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
    expect(csvCell('o "x" o')).toBe('"o ""x"" o"')
    expect(csvCell(null)).toBe('')
    expect(csvCell(0)).toBe('0')
  })

  it('csvCell: kayan nokta artığı ayıklanır, gerçek değer ve metin ücretler bozulmaz', () => {
    expect(csvCell(1146.2248000000002)).toBe('1146.2248')
    expect(csvCell(314.763)).toBe('314.763')
    expect(csvCell(0.8)).toBe('0.8')
    expect(csvCell(1 / 3)).toBe('0.333333333333')
    expect(csvCell('0.000193326')).toBe('0.000193326') // ücret metin olarak taşınır, yuvarlanmaz
  })

  it('Markdown: kaynak, örnek kapsamı, sürümler, tablo ve okuma notları', () => {
    const md = buildMarkdown(detail)

    expect(md).toContain('5 sentetik geliştirme örneği — bağlantı denemesi')
    expect(md).toContain('jev-1.13.0')
    expect(md).toContain('claude-haiku-4-5-20251001')
    expect(md).toContain('Hibrit v1 — kayıtta sürüm yok, eski yönlendirme')
    expect(md).toContain('| Ölçüt | Jev | LLM | Hibrit |')
    expect(md).toContain('| Kategori doğruluğu | %100,0 (5/5) | %100,0 (5/5) | %100,0 (5/5) |')
    expect(md).toContain('Küçük örneklem')
    expect(md).toContain("v2'nin daha iyi olduğuna dair henüz gerçek ölçüm yoktur")
    expect(md).toContain('tokenizer')
    expect(md).toContain('(tahmin)')
  })

  it('Markdown tablo hücresindeki | karakteri kaçışlanır (başlık hücresi dahil)', () => {
    const tricky = withStrategy(detail, 'jev_only', (s) => ({
      ...s,
      info: { ...s.info, kind: 'ozel', name: 'a|b' },
    }))
    expect(buildMarkdown(tricky)).toContain('| Ölçüt | a\\|b | LLM | Hibrit |')
  })
})

describe('örnek süzgeçleri', () => {
  const detail = makeDetail()

  it('"yanlış tahmin" yalnızca en az bir stratejinin ayrıldığı örnekleri getirir', () => {
    expect(filterSamples(detail.samples, 'wrong').map((r) => r.id)).toEqual(['s023'])
  })

  it('"tartışmalı" yalnızca işaretli etiketleri getirir', () => {
    expect(filterSamples(detail.samples, 'disputed').map((r) => r.id)).toEqual(['s023'])
  })

  it('"incelemeye gönderilen" ve "tümü"', () => {
    expect(filterSamples(detail.samples, 'review')).toEqual([])
    expect(filterSamples(detail.samples, 'all')).toHaveLength(5)
  })

  it('varsayılan örnek: stratejilerin ayrıştığı örnek yoksa tartışmalı olmayan ilk ortak örnek', () => {
    // Üç strateji aynı tahmini verdi (s023 dahil); tartışmalı etiketli örnek sona bırakılır.
    expect(defaultExampleId(detail)).toBe('s003')
  })

  it('stratejiler ayrışıyorsa o örnek seçilir', () => {
    const differing = {
      ...detail,
      samples: detail.samples.map((r) =>
        r.id === 's051'
          ? {
              ...r,
              strategies: {
                ...r.strategies,
                hybrid: { ...r.strategies.hybrid!, priority: 'high' },
              },
            }
          : r,
      ),
    }
    expect(defaultExampleId(differing)).toBe('s051')
  })

  it('örnek yoksa null', () => {
    expect(defaultExampleId({ ...detail, samples: [] })).toBeNull()
  })

  it('liste yardımcısı tek deneyi döndürür', () => {
    expect(makeList().runs).toHaveLength(1)
  })
})

import { describe, expect, it } from 'vitest'

import { RUN_ID, jevInfo, makeDetail, makeList, makeRun, makeSample } from '../experiment-fixtures'
import {
  jevStrategy,
  loadRecordedExample,
  pickRecordedRun,
  recordedSampleIds,
  recordedUsage,
} from './recorded-example'
import { createStaticSource } from './static-experiments'

const PRICES = makeDetail().conditions?.prices ?? []

function jev() {
  const strategy = jevStrategy(makeSample())
  if (!strategy) throw new Error('fixture: Jev stratejisi yok')
  return strategy
}

describe('pickRecordedRun', () => {
  it('yalnızca tamamlanmış, gerçek sağlayıcılı ve mock olmayan Jev içeren deneyi seçer', () => {
    const mock = makeRun({ id: 'mock', strategies: [{ ...jevInfo, is_mock: true }] })
    const partial = makeRun({ id: 'yarim', status: 'partial' })
    const offline = makeRun({ id: 'cevrimdisi', live: false })
    const good = makeRun({ id: 'iyi' })

    expect(pickRecordedRun(makeList([mock, partial, offline, good]))?.id).toBe('iyi')
    expect(pickRecordedRun(makeList([mock, partial]))).toBeNull()
    expect(pickRecordedRun(makeList([]))).toBeNull()
  })
})

describe('recordedSampleIds', () => {
  it('tartışmalı etiketli ve Jev kararı başarısız olan örnekleri dışarıda bırakır', () => {
    const detail = makeDetail()
    detail.samples[0].strategies.jev_only = { ...detail.samples[0].strategies.jev_only!, failed: true }

    const ids = recordedSampleIds(detail)

    expect(ids).not.toContain('s003') // Jev başarısız
    expect(ids).not.toContain('s023') // tartışmalı etiket
    expect(ids).toEqual(['s009', 's020', 's051'])
  })

  it('ölçüm yoksa örnek de yok', () => {
    expect(recordedSampleIds(makeDetail({ metrics_available: false }))).toEqual([])
  })
})

describe('recordedUsage', () => {
  it('bildirilen kullanımı canlı sonuçla aynı biçime çevirir; fiyat notunda kontrol tarihi var', () => {
    const usage = recordedUsage(jev(), PRICES)

    expect(usage).toMatchObject({
      input_tokens: 4603,
      output_tokens: 902,
      output_tokens_free: true,
      cost_usd: '0.000038682',
      cost_basis: 'provider_usage',
    })
    expect(usage?.price_note).toContain('kontrol')
  })

  it('ücreti bilinmeyen veya tahmini kullanımlı çağrı varsa ücret null ("bilinmiyor"), sıfır değil', () => {
    const strategy = jev()
    const unknown = { ...strategy, calls_with_unknown_cost: 1 }
    const estimated = { ...strategy, usage: [{ ...strategy.usage[0], usage_estimated_calls: 1 }] }

    for (const item of [unknown, estimated]) {
      const usage = recordedUsage(item, PRICES)
      expect(usage?.cost_usd).toBeNull()
      expect(usage?.cost_basis).toBe('unknown')
    }
  })

  it('token bildirilmeyen çağrı varsa token null', () => {
    const strategy = jev()
    const usage = recordedUsage(
      { ...strategy, usage: [{ ...strategy.usage[0], calls_without_input_usage: 1 }] },
      PRICES,
    )

    expect(usage?.input_tokens).toBeNull()
    expect(usage?.output_tokens).toBe(902)
  })

  it('kullanım kaydı yoksa null', () => {
    expect(recordedUsage({ ...jev(), usage: [] }, PRICES)).toBeNull()
  })
})

describe('loadRecordedExample', () => {
  it('statik kaynaktan uygun örnekleri hazırlar; dosyada olmayan örnek atlanır', async () => {
    const s009 = makeSample()
    s009.sample = { ...s009.sample, id: 's009', disputed: null }
    const source = createStaticSource({
      list: makeList(),
      details: { [RUN_ID]: makeDetail() },
      samples: { [RUN_ID]: { s009, s023: makeSample() } },
    })

    const example = await loadRecordedExample(source)

    expect(example?.run.id).toBe(RUN_ID)
    expect(example?.samples.map((item) => item.sample.id)).toEqual(['s009'])
    expect(example?.samples[0].jev.info.kind).toBe('jev_only')
  })

  it('uygun kayıt yoksa null (kart gösterilmez, uydurma değer yok)', async () => {
    const source = createStaticSource({
      list: makeList(),
      details: { [RUN_ID]: makeDetail() },
      samples: { [RUN_ID]: { s023: makeSample() } },
    })

    expect(await loadRecordedExample(source)).toBeNull()
  })
})

import type { ExperimentSource } from './api'
import type { DemoUsage } from './demo-types'
import type {
  ExperimentDetail,
  ExperimentList,
  ExperimentPrice,
  ExperimentRun,
  ExperimentSample,
  SampleStrategy,
} from './experiment-types'

/**
 * Canlı deneme kapalıyken gösterilen "Kayıtlı örnek": önceden kaydedilmiş gerçek bir deneyde Jev'in
 * tek bir örnek talep için verdiği karar. Yalnızca statik dosyadan OKUNUR; model çağrısı yapılmaz ve
 * hiçbir değer tahmin edilmez. Uygun kayıt yoksa null döner (arayüz bu durumda kart göstermez).
 */
export interface RecordedSample {
  sample: ExperimentSample['sample']
  jev: SampleStrategy
  usage: DemoUsage | null
}

export interface RecordedExample {
  run: ExperimentRun
  samples: RecordedSample[]
}

/** Kaç örneğin kartı hazırlanır (statik dosya büyürse sayfa gereksiz iş yapmasın). */
export const RECORDED_LIMIT = 10

/** Tamamlanmış, gerçek sağlayıcıyla alınmış ve mock olmayan Jev stratejisi içeren ilk deney. */
export function pickRecordedRun(list: ExperimentList): ExperimentRun | null {
  return (
    list.runs.find(
      (run) =>
        run.status === 'complete' &&
        run.live &&
        run.strategies.some((info) => info.kind === 'jev_only' && !info.is_mock),
    ) ?? null
  )
}

/** Karşılaştırmaya giren, etiketi tartışmalı olmayan ve Jev kararı başarıyla kaydedilmiş örnekler. */
export function recordedSampleIds(detail: ExperimentDetail): string[] {
  if (!detail.metrics_available) return []
  const jev = detail.strategies.find((result) => result.info.kind === 'jev_only' && !result.info.is_mock)
  if (!jev) return []
  return detail.samples
    .filter((row) => {
      const cell = row.strategies[jev.name]
      return row.in_common && !row.disputed && cell !== undefined && cell !== null && !cell.failed
    })
    .map((row) => row.id)
}

/** Örnekteki gerçek (mock olmayan) ve başarılı Jev kararı. */
export function jevStrategy(sample: ExperimentSample): SampleStrategy | null {
  return (
    sample.strategies.find(
      (strategy) => strategy.info.kind === 'jev_only' && strategy.present && !strategy.failed && strategy.is_mock === false,
    ) ?? null
  )
}

function priceNote(prices: ExperimentPrice[], model: string | null): string {
  const price = prices.find((item) => item.provider === 'jev' && (model === null || item.model === model))
  if (!price) return 'Fiyat bilgisi kayıtta yok.'
  const input = price.input_usd_per_mtok.replace('.', ',')
  const output = price.output_usd_per_mtok === '0' ? 'çıktı tokenları ücretsiz' : `çıktı ${price.output_usd_per_mtok.replace('.', ',')} USD`
  return `Jev (${price.model}): ${input} USD / 1 milyon GİRDİ tokenı; ${output} (fiyat kontrolü: ${price.checked_on ?? 'tarih yok'}).`
}

/**
 * Kayıttaki sağlayıcı kullanımını canlı sonuçla aynı biçime çevirir. Token bildirilmeyen çağrı varsa
 * token null; ücreti bilinmeyen veya tahmini kullanımlı çağrı varsa ücret null ("bilinmiyor", sıfır değil).
 */
export function recordedUsage(strategy: SampleStrategy, prices: ExperimentPrice[]): DemoUsage | null {
  const parts = strategy.usage
  if (parts.length === 0) return null
  const sum = (pick: (part: (typeof parts)[number]) => number) => parts.reduce((total, part) => total + pick(part), 0)
  const inputKnown = parts.every((part) => part.calls_without_input_usage === 0)
  const outputKnown = parts.every((part) => part.calls_without_output_usage === 0)
  const costKnown =
    strategy.cost_known_usd !== null &&
    (strategy.calls_with_unknown_cost ?? 0) === 0 &&
    parts.every((part) => part.calls_with_unknown_cost === 0 && part.usage_estimated_calls === 0)
  return {
    calls: sum((part) => part.calls),
    input_tokens: inputKnown ? sum((part) => part.input_tokens) : null,
    output_tokens: outputKnown ? sum((part) => part.output_tokens) : null,
    output_tokens_free: parts.every((part) => part.output_tokens_free),
    cost_usd: costKnown ? strategy.cost_known_usd : null,
    cost_basis: costKnown ? 'provider_usage' : 'unknown',
    price_note: priceNote(prices, strategy.info.model),
  }
}

/** Statik kaynaktan kayıtlı örnekleri hazırlar; uygun kayıt yoksa null. */
export async function loadRecordedExample(source: ExperimentSource): Promise<RecordedExample | null> {
  const run = pickRecordedRun(await source.listExperiments())
  if (!run) return null
  const detail = await source.getExperiment(run.id)
  const ids = recordedSampleIds(detail).slice(0, RECORDED_LIMIT)
  const loaded = await Promise.all(ids.map((id) => source.getExperimentSample(run.id, id).catch(() => null)))
  const prices = detail.conditions?.prices ?? []
  const samples: RecordedSample[] = []
  for (const item of loaded) {
    const jev = item ? jevStrategy(item) : null
    if (item && jev) samples.push({ sample: item.sample, jev, usage: recordedUsage(jev, prices) })
  }
  return samples.length > 0 ? { run, samples } : null
}

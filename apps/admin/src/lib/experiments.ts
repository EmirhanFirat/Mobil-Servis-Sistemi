import { questionText } from './decision'
import type {
  ExperimentDetail,
  ExperimentRun,
  ExperimentStatus,
  ExperimentStrategyInfo,
  HybridRouting,
  Proportion,
  SampleRow,
  StrategyResult,
} from './experiment-types'
import { formatDateTime } from './format'

/** Değer bilinmiyor (sıfır DEĞİL). */
export const UNKNOWN = 'bilinmiyor'
/** Bu strateji için geçerli bir değer yok (ör. LLM'e geçiş oranı, Jev tek başınayken). */
export const NA = '—'

// --- adlar ---

export function strategyTitle(info: ExperimentStrategyInfo): string {
  const base =
    info.kind === 'jev_only'
      ? 'Jev'
      : info.kind === 'llm_only'
        ? 'LLM'
        : info.kind === 'hybrid'
          ? 'Hibrit'
          : info.kind === 'rule_based'
            ? 'Kural tabanlı'
            : info.name
  return info.is_mock ? `${base} (MOCK)` : base
}

/** Kayıtlı gerçek model sürümü; takma ad değil. */
export function strategyModelLine(info: ExperimentStrategyInfo): string {
  if (info.kind === 'hybrid') {
    return [info.jev?.model, info.llm?.model].filter(Boolean).join(' + ') || NA
  }
  return info.model ?? info.prompt_version ?? NA
}

const STATUS_TEXT: Record<ExperimentStatus, string> = {
  complete: 'Tamamlandı',
  partial: 'Yarım kaldı',
  missing_files: 'Kayıtlar eksik',
  corrupt: 'Bozuk kayıt',
}

export function statusText(status: ExperimentStatus): string {
  return STATUS_TEXT[status] ?? status
}

/** Hibrit yönlendirme sürümü; kayıtta alan yoksa açıkça "v1 (eski)" denir. */
export function routingLabel(routing: HybridRouting | null): string {
  if (!routing) return NA
  const short = routing.version.replace('hibrit-yonlendirme-', 'Hibrit ')
  return routing.recorded ? short : `${short} — kayıtta sürüm yok, eski yönlendirme`
}

export function providerLabel(provider: string): string {
  const known: Record<string, string> = { jev: 'Jev', anthropic: 'Anthropic' }
  return known[provider] ?? provider
}

// --- sayı biçimleri (tr-TR; kayan noktaya güvenmeden) ---

function group(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

export function formatCount(n: number): string {
  return group(String(Math.round(n)))
}

/** Ondalık METNİ (ör. "0.000038") tr-TR yapar: en az 4, sondaki gereksiz sıfırlar atılır. */
export function decimalText(value: string, minDecimals = 4): string {
  const [whole, fraction = ''] = value.split('.')
  let trimmed = fraction.replace(/0+$/, '')
  if (trimmed.length < minDecimals) trimmed = trimmed.padEnd(minDecimals, '0')
  return `${group(whole)},${trimmed}`
}

/** Para birimiyle; bilinmeyen değer "bilinmiyor" (sıfır değil). */
export function formatUsd(value: string | null | undefined): string {
  return value === null || value === undefined ? UNKNOWN : `${decimalText(value)} USD`
}

export function formatPercent(p: Proportion): string {
  if (p.value === null) return NA
  return `%${(p.value * 100).toFixed(1).replace('.', ',')} (${p.successes}/${p.n})`
}

export function formatMs(value: number | null): string {
  return value === null ? UNKNOWN : `${formatCount(value)} ms`
}

export function formatScore(value: number | null): string {
  return value === null ? UNKNOWN : value.toFixed(2).replace('.', ',')
}

// --- karşılaştırma tablosu: ekran, CSV ve Markdown aynı satırlardan üretilir ---

export interface ComparisonRow {
  key: string
  label: string
  group: 'kapsam' | 'dogruluk' | 'karar' | 'sure' | 'ucret' | 'token' | 'cagri' | 'hibrit'
  cells: Record<string, string>
  /** Satır başlığının altındaki kısa açıklama. */
  note?: string
}

function perStrategy(detail: ExperimentDetail, fn: (result: StrategyResult) => string): Record<string, string> {
  return Object.fromEntries(detail.strategies.map((result) => [result.name, fn(result)]))
}

function outputTokenText(result: StrategyResult): string {
  const total = formatCount(result.usage.output_tokens)
  const free = result.usage.providers.filter((p) => p.output_tokens_free).reduce((sum, p) => sum + p.output_tokens, 0)
  if (free === 0) return total
  if (free === result.usage.output_tokens) return `${total} (tamamı ücretsiz çıktı)`
  return `${total} (${formatCount(free)} tanesi ücretsiz çıktı)`
}

function providerSplit(result: StrategyResult): string {
  if (result.usage.providers.length < 2) return NA
  return result.usage.providers
    .map(
      (p) =>
        `${providerLabel(p.provider)}: ${formatCount(p.input_tokens)} giriş / ${formatCount(p.output_tokens)} çıkış`,
    )
    .join(' · ')
}

function costText(result: StrategyResult): string {
  const { known_usd, calls_with_unknown_cost } = result.cost
  if (calls_with_unknown_cost > 0) {
    return `${formatUsd(known_usd)} bilinen + ${calls_with_unknown_cost} çağrının ücreti bilinmiyor`
  }
  return formatUsd(known_usd)
}

function triggerText(result: StrategyResult): string {
  if (!result.hybrid) return NA
  const entries = Object.entries(result.hybrid.trigger_questions)
  if (entries.length === 0) return "LLM'e geçiş olmadı"
  return entries.map(([question, count]) => `${questionText(question)} (${count})`).join(' · ')
}

export function comparisonRows(detail: ExperimentDetail): ComparisonRow[] {
  const rows: ComparisonRow[] = [
    {
      key: 'n',
      label: 'Karşılaştırılan talep',
      group: 'kapsam',
      note: 'Yalnızca tüm stratejilerin ortak tamamladığı örnekler',
      cells: perStrategy(detail, (r) => String(r.n)),
    },
    {
      key: 'category_accuracy',
      label: 'Kategori doğruluğu',
      group: 'dogruluk',
      cells: perStrategy(detail, (r) => formatPercent(r.metrics.category_accuracy)),
    },
    {
      key: 'category_macro_f1',
      label: 'Kategori macro-F1',
      group: 'dogruluk',
      cells: perStrategy(detail, (r) => formatScore(r.metrics.category_macro_f1)),
    },
    {
      key: 'priority_accuracy',
      label: 'Öncelik doğruluğu',
      group: 'dogruluk',
      cells: perStrategy(detail, (r) => formatPercent(r.metrics.priority_accuracy)),
    },
    {
      key: 'high_priority_missed',
      label: 'Yüksek öncelikli talebi kaçırma',
      group: 'dogruluk',
      note: 'kaçırılan / etiketli yüksek öncelikli',
      cells: perStrategy(detail, (r) => {
        const { successes, n } = r.metrics.high_priority_recall
        return n === 0 ? NA : `${n - successes} / ${n}`
      }),
    },
    {
      key: 'review_rate',
      label: 'İncelemeye gönderme',
      group: 'karar',
      cells: perStrategy(detail, (r) => formatPercent(r.metrics.review_rate)),
    },
    {
      key: 'automated_rate',
      label: 'Otomatik karar',
      group: 'karar',
      cells: perStrategy(detail, (r) => formatPercent(r.metrics.automated_rate)),
    },
    {
      key: 'latency_p50',
      label: 'Karar süresi p50',
      group: 'sure',
      note: 'uçtan uca (ağ ve yeniden deneme dahil)',
      cells: perStrategy(detail, (r) => formatMs(r.metrics.latency_p50_ms)),
    },
    {
      key: 'latency_p95',
      label: 'Karar süresi p95',
      group: 'sure',
      cells: perStrategy(detail, (r) => formatMs(r.metrics.latency_p95_ms)),
    },
    {
      key: 'cost_known',
      label: 'Toplam bilinen model ücreti (ölçülen)',
      group: 'ucret',
      note: 'sağlayıcının bildirdiği kullanımdan hesaplanır',
      cells: perStrategy(detail, costText),
    },
    {
      key: 'cost_per_completed',
      label: 'Tamamlanan talep başına ücret (ölçülen)',
      group: 'ucret',
      cells: perStrategy(detail, (r) => formatUsd(r.cost.per_completed_usd)),
    },
    {
      key: 'cost_estimate_1000',
      label: '1.000 talebe ölçeklenen TAHMİN',
      group: 'ucret',
      note: 'ölçülen değil; talep başına ücret × 1.000. Küçük örneklemden kanıt sayılmaz',
      cells: perStrategy(detail, (r) =>
        r.cost.estimate_per_1000_usd === null ? UNKNOWN : `${formatUsd(r.cost.estimate_per_1000_usd)} (tahmin)`,
      ),
    },
    {
      key: 'input_tokens',
      label: 'Girdi tokenı',
      group: 'token',
      note: "sağlayıcı bildirimi; tokenizer'lar eşdeğer değildir",
      cells: perStrategy(detail, (r) =>
        r.usage.calls_without_usage > 0
          ? `${formatCount(r.usage.input_tokens)} (${r.usage.calls_without_usage} çağrı bildirmedi)`
          : formatCount(r.usage.input_tokens),
      ),
    },
    {
      key: 'output_tokens',
      label: 'Çıktı tokenı',
      group: 'token',
      cells: perStrategy(detail, outputTokenText),
    },
    {
      key: 'provider_split',
      label: 'Sağlayıcı bazında token (hibrit)',
      group: 'token',
      cells: perStrategy(detail, providerSplit),
    },
    {
      key: 'calls',
      label: 'Çağrı / retry / çağrı hatası',
      group: 'cagri',
      cells: perStrategy(detail, (r) => `${r.usage.calls} / ${r.usage.retries} / ${r.usage.call_errors}`),
    },
    {
      key: 'failed_decisions',
      label: 'Başarısız karar',
      group: 'cagri',
      cells: perStrategy(detail, (r) => String(r.n_failed)),
    },
    {
      key: 'escalation_rate',
      label: "Hibritte LLM'e geçiş oranı",
      group: 'hibrit',
      cells: perStrategy(detail, (r) => (r.hybrid ? formatPercent(r.hybrid.escalated) : NA)),
    },
    {
      key: 'escalation_questions',
      label: 'Geçişi tetikleyen sorular',
      group: 'hibrit',
      note: "LLM'e gönderilen sorular (örnek sayısı)",
      cells: perStrategy(detail, triggerText),
    },
  ]
  return rows
}

// --- kapsam ve dosya adı ---

/** "5 sentetik geliştirme örneği — bağlantı denemesi" (sunucu üretir; yoksa güvenli yedek metin). */
export function scopeLabel(run: ExperimentRun): string {
  if (run.scope_label) return run.scope_label
  const n = run.dataset?.n_completed ?? run.dataset?.n_samples
  return n === null || n === undefined ? 'Örnek sayısı bilinmiyor' : `${n} örnek`
}

export function runDate(run: ExperimentRun): string {
  return run.created_at ? formatDateTime(run.created_at) : UNKNOWN
}

export function runOptionText(run: ExperimentRun): string {
  const strategies = run.strategies.map((s) => strategyTitle(s)).join(' + ')
  return `${runDate(run)} · ${scopeLabel(run)} · ${strategies} · ${statusText(run.status)}`
}

export function exportFileName(run: ExperimentRun, extension: 'csv' | 'md' | 'png'): string {
  return `model-karsilastirma-${run.id}.${extension}`
}

// --- örnek süzgeçleri ---

export type SampleFilter = 'all' | 'wrong' | 'disputed' | 'review'

export const SAMPLE_FILTERS: { key: SampleFilter; label: string }[] = [
  { key: 'all', label: 'Tüm örnekler' },
  { key: 'wrong', label: 'En az bir stratejinin yanlış tahmin ettikleri' },
  { key: 'disputed', label: 'Tartışmalı etiketliler' },
  { key: 'review', label: 'En az birinin incelemeye gönderdikleri' },
]

export function filterSamples(rows: SampleRow[], filter: SampleFilter): SampleRow[] {
  switch (filter) {
    case 'wrong':
      return rows.filter((row) =>
        Object.values(row.strategies).some(
          (cell) => cell !== null && (cell.category_ok === false || cell.priority_ok === false),
        ),
      )
    case 'disputed':
      return rows.filter((row) => row.disputed !== null)
    case 'review':
      return rows.filter((row) => Object.values(row.strategies).some((cell) => cell?.review_required === true))
    default:
      return rows
  }
}

/**
 * Paylaşım görünümünün varsayılan örnek talebi: stratejilerin birbirinden ayrıldığı ilk ortak
 * örnek (tartışmalı etiketli olanlar sona bırakılır); yoksa ilk ortak örnek.
 */
export function defaultExampleId(detail: ExperimentDetail): string | null {
  const common = detail.samples.filter((row) => row.in_common)
  const differs = (row: SampleRow) => {
    const cells = Object.values(row.strategies).filter((c) => c !== null)
    return new Set(cells.map((c) => `${c?.category}|${c?.priority}`)).size > 1
  }
  const ordered = [...common].sort((a, b) => Number(a.disputed !== null) - Number(b.disputed !== null))
  return (ordered.find(differs) ?? ordered[0] ?? null)?.id ?? null
}

// --- dışa aktarma ---

export function csvCell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return '' // bilinmeyen: boş (0 değil)
  // Kayan nokta artığını (1146.2248000000002) ayıkla; 12 anlamlı basamak ölçümün hassasiyetinin çok üstünde.
  const text =
    typeof value === 'number' && Number.isFinite(value) ? String(Number(value.toPrecision(12))) : String(value)
  return /[",\r\n;]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function num(p: Proportion): number | null {
  return p.value
}

/** Her satır bir strateji; sayılar nokta ondalıklı ve birimsiz (veri analizi için). */
export function buildCsv(detail: ExperimentDetail): string {
  const run = detail.run
  const header = [
    'deney_id',
    'deney_tarihi',
    'veri_kaynagi',
    'ornek_kapsami',
    'hibrit_yonlendirme_surumu',
    'strateji',
    'model',
    'karsilastirilan_talep',
    'kategori_dogrulugu',
    'kategori_macro_f1',
    'oncelik_dogrulugu',
    'yuksek_oncelik_kacirilan',
    'yuksek_oncelik_etiketli',
    'incelemeye_gonderme_orani',
    'otomatik_karar_orani',
    'karar_suresi_p50_ms',
    'karar_suresi_p95_ms',
    'olculen_toplam_ucret_usd',
    'ucreti_bilinmeyen_cagri',
    'talep_basi_ucret_usd',
    'tahmini_1000_talep_ucreti_usd_TAHMIN',
    'girdi_token',
    'cikti_token',
    'cagri',
    'retry',
    'cagri_hatasi',
    'basarisiz_karar',
    'hibrit_llm_gecis_orani',
    'hibrit_llm_gecis_sorulari',
  ]
  const lines = [header.join(',')]
  for (const r of detail.strategies) {
    const m = r.metrics
    const triggers = r.hybrid
      ? Object.entries(r.hybrid.trigger_questions)
          .map(([q, c]) => `${q}:${c}`)
          .join(' ')
      : null
    const cells = [
      run.id,
      run.created_at,
      run.dataset?.source,
      scopeLabel(run),
      run.hybrid_routing ? run.hybrid_routing.version + (run.hybrid_routing.recorded ? '' : ' (kayıtta yok)') : null,
      r.name,
      strategyModelLine(r.info),
      r.n,
      num(m.category_accuracy),
      m.category_macro_f1,
      num(m.priority_accuracy),
      m.high_priority_recall.n - m.high_priority_recall.successes,
      m.high_priority_recall.n,
      num(m.review_rate),
      num(m.automated_rate),
      m.latency_p50_ms,
      m.latency_p95_ms,
      r.cost.calls_with_unknown_cost > 0 ? null : r.cost.known_usd,
      r.cost.calls_with_unknown_cost,
      r.cost.per_completed_usd,
      r.cost.estimate_per_1000_usd,
      r.usage.input_tokens,
      r.usage.output_tokens,
      r.usage.calls,
      r.usage.retries,
      r.usage.call_errors,
      r.n_failed,
      r.hybrid ? num(r.hybrid.escalated) : null,
      triggers,
    ]
    lines.push(cells.map(csvCell).join(','))
  }
  // BOM: Excel Türkçe karakterleri doğru okusun.
  return `﻿${lines.join('\r\n')}\r\n`
}

function mdCell(text: string): string {
  return text.replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
}

/** Medium/GitHub'da yapıştırılabilir sonuç tablosu ve dürüst okuma notları. */
export function buildMarkdown(detail: ExperimentDetail): string {
  const run = detail.run
  const results = detail.strategies
  const rows = comparisonRows(detail)
  const lines: string[] = [
    '## Jev, LLM ve hibrit: Türkçe servis talepleri karşılaştırması',
    '',
    `**Veri:** ${scopeLabel(run)} · **Deney tarihi:** ${runDate(run)} · **Deney kimliği:** \`${run.id}\``,
    '',
    `**Modeller:** ${results.map((r) => `${strategyTitle(r.info)} = ${strategyModelLine(r.info)}`).join(' · ')}`,
    '',
  ]
  if (run.hybrid_routing) {
    lines.push(`**Hibrit yönlendirme:** ${routingLabel(run.hybrid_routing)}. ${run.hybrid_routing.description}`, '')
  }
  lines.push(
    '| Ölçüt | ' + results.map((r) => mdCell(strategyTitle(r.info))).join(' | ') + ' |',
    '|---|' + results.map(() => '---|').join(''),
  )
  for (const row of rows) {
    lines.push(`| ${mdCell(row.label)} | ${results.map((r) => mdCell(row.cells[r.name] ?? NA)).join(' | ')} |`)
  }
  lines.push('', '### Okuma notları', '')
  for (const warning of detail.warnings) lines.push(`- ${warning.text}`)
  lines.push(
    `- ${detail.notes.tokens}`,
    '- "1.000 talebe ölçeklenen" satırı ölçülmüş değil, talep başına ölçülen ücretin 1.000 ile çarpımıdır (tahmin).',
    '- Kaynak: TalepAkış yönetici paneli, Model karşılaştırma ekranı; kayıtlı deney dosyalarından (run.json, predictions.jsonl) hesaplanmıştır.',
    '',
  )
  return lines.join('\n')
}

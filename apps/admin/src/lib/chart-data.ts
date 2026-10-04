import type { StrategyResult } from './experiment-types'
import { UNKNOWN, decimalText, formatCount, strategyTitle } from './experiments'

/** Grafik ve paylaşım kartı için sabitler ve veri üreticileri (bileşen olmayan kodlar burada durur). */

export const FONT = "system-ui, 'Segoe UI', Roboto, Arial, sans-serif"
export const INK = '#111827'
export const MUTED = '#5b6472'
export const GRID = '#e1e4ea'

/** Renk körlüğüne dayanıklı, birbirinden ayrı üç renk. */
export function strategyColor(kind: string | null, index: number): string {
  if (kind === 'jev_only') return '#1d4ed8'
  if (kind === 'llm_only') return '#c2410c'
  if (kind === 'hybrid') return '#047857'
  return ['#6d28d9', '#475569', '#be185d'][index % 3]
}

/** Çubuk yüksekliği (piksel). Bilinmeyen değerde 0; pozitif çok küçük değer görünür kalsın diye en az 3. */
export function barPixels(value: number | null, max: number, plot: number): number {
  if (value === null || max <= 0 || value <= 0) return 0
  return Math.max(3, (value / max) * plot)
}

export interface BarItem {
  key: string
  label: string
  value: number | null
  text: string
  color: string
}

export interface PairItem {
  key: string
  label: string
  first: number | null
  firstText: string
  second: number | null
  secondText: string
  color: string
}

function toNumber(value: string | null): number | null {
  if (value === null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Tamamlanan talep başına ölçülen ücret (USD). Çubuk ölçeği yalnızca çizim içindir; yazı tam ondalık metindir. */
export function costBarItems(results: StrategyResult[]): BarItem[] {
  return results.map((r, index) => ({
    key: r.name,
    label: strategyTitle(r.info),
    value: toNumber(r.cost.per_completed_usd),
    text: r.cost.per_completed_usd === null ? UNKNOWN : decimalText(r.cost.per_completed_usd),
    color: strategyColor(r.info.kind, index),
  }))
}

/** Uçtan uca karar süresi p50/p95 (ms). */
export function latencyPairItems(results: StrategyResult[]): PairItem[] {
  return results.map((r, index) => ({
    key: r.name,
    label: strategyTitle(r.info),
    first: r.metrics.latency_p50_ms,
    firstText: r.metrics.latency_p50_ms === null ? UNKNOWN : formatCount(r.metrics.latency_p50_ms),
    second: r.metrics.latency_p95_ms,
    secondText: r.metrics.latency_p95_ms === null ? UNKNOWN : formatCount(r.metrics.latency_p95_ms),
    color: strategyColor(r.info.kind, index),
  }))
}

/** Paylaşım kartının genişliği (piksel). */
export const SHARE_WIDTH = 1200

/** Paylaşım görselinde yer alan ölçütler (uzun satırlar ve tahmini ölçekleme bilerek çıkarıldı). */
export const SHARE_KEYS = [
  'n',
  'category_accuracy',
  'category_macro_f1',
  'priority_accuracy',
  'high_priority_missed',
  'review_rate',
  'automated_rate',
  'latency_p50',
  'latency_p95',
  'cost_known',
  'cost_per_completed',
  'input_tokens',
  'output_tokens',
  'calls',
  'escalation_rate',
]

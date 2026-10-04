import { SHARE_KEYS, SHARE_WIDTH } from './chart-data'
import { questionText } from './decision'
import type { ExperimentDetail, ExperimentSample, SampleStrategy } from './experiment-types'
import {
  NA,
  UNKNOWN,
  type ComparisonRow,
  comparisonRows,
  routingLabel,
  runDate,
  scopeLabel,
  strategyModelLine,
  strategyTitle,
} from './experiments'
import { wrapText } from './image-export'

export const PAD = 40
export const LABEL_COL = 360
const FOOTER_CHARS = 175
const LABEL_CHARS = 44
const ESCALATION_CHARS = 30
const ESCALATION_MAX_LINES = 3
export const ESCALATION_LABEL = "LLM'e giden:"

const LABEL_STATUS_TR: Record<string, string> = {
  single_annotator_unreviewed: 'tek kişiyce yazıldı, gözden geçirilmedi',
}
const SOURCE_TR: Record<string, string> = { synthetic: 'sentetik' }

/** Hibritin LLM'e gönderdiği soruları örnek sütununa sığacak satırlara böler (hibrit değilse boş). */
export function escalationLines(strategy: SampleStrategy): string[] {
  if (strategy.info.kind !== 'hybrid' || !strategy.present || strategy.failed) return []
  const asked = strategy.escalated_questions.map((q) => questionText(q).replace(/\?$/, ''))
  return wrapText(
    `${ESCALATION_LABEL} ${asked.length > 0 ? asked.join(', ') : 'yok'}`,
    ESCALATION_CHARS,
    ESCALATION_MAX_LINES,
  )
}

/** Tablo satırının yüksekliği: etiket veya herhangi bir hücre ikinci satıra sarıldıysa yüksek satır. */
export function rowHeight(labelLines: string[], cells: string[][]): number {
  const lines = Math.max(labelLines.length, ...cells.map((c) => c.length))
  return lines > 1 ? 52 : 34
}

export interface RowLayout {
  row: ComparisonRow
  labelLines: string[]
  wrapped: string[][]
  height: number
  top: number
}

export interface ShareLayout {
  headerY: number
  scope: string
  warn: boolean
  pillWidth: number
  colWidth: number
  tableTop: number
  rows: RowLayout[]
  chartTop: number
  exampleTop: number
  textLines: string[]
  exampleHeight: number
  footerTop: number
  footer: string[]
  height: number
}

/** Paylaşım kartının dikey yerleşimi (saf hesap: aynı veri → aynı yerleşim). */
export function computeShareLayout(detail: ExperimentDetail, example: ExperimentSample | null): ShareLayout {
  const run = detail.run
  const results = detail.strategies
  const comparison = comparisonRows(detail).filter((row) => SHARE_KEYS.includes(row.key))

  const headerY = 36
  const scope = scopeLabel(run)
  const warn = /bağlantı denemesi|küçük|MOCK/.test(scope)
  const pillWidth = Math.min(SHARE_WIDTH - 2 * PAD, scope.length * 9 + 36)
  const colWidth = (SHARE_WIDTH - 2 * PAD - LABEL_COL) / Math.max(results.length, 1)

  const tableTop = headerY + 112
  let cursor = tableTop + 62
  const rows: RowLayout[] = comparison.map((row) => {
    const labelLines = wrapText(row.label, LABEL_CHARS, 2)
    const wrapped = results.map((r) => wrapText(row.cells[r.name] ?? NA, 30, 2))
    const height = rowHeight(labelLines, wrapped)
    const top = cursor
    cursor += height
    return { row, labelLines, wrapped, height, top }
  })

  const chartTop = cursor + 26
  const exampleTop = chartTop + 262 + 24
  const textLines = example
    ? [
        ...wrapText(`Başlık: ${example.sample.title}`, 48, 2),
        ...wrapText(`Açıklama: ${example.sample.description}`, 48, 5),
        ...wrapText(`Konum: ${example.sample.location}`, 48, 2),
      ]
    : []
  // Örnek sütunları: ilk satır kutu üstünden 14 px aşağıda; 6. satırın (hibrit) tabanı +166, her ek satır ~19,6 px.
  const columnLines = example ? Math.max(1, ...example.strategies.map((s) => escalationLines(s).length)) : 1
  const columnsHeight = Math.ceil(14 + 166 + (columnLines - 1) * 19.6 + 24)
  const exampleHeight = example ? Math.max(220, 120 + textLines.length * 21 + 40, columnsHeight) : 60
  const footerTop = exampleTop + 38 + exampleHeight + 22

  const source = SOURCE_TR[run.dataset?.source ?? ''] ?? run.dataset?.source ?? UNKNOWN
  const labelState = LABEL_STATUS_TR[run.dataset?.label_status ?? ''] ?? run.dataset?.label_status ?? UNKNOWN
  const footer: string[] = [
    ...wrapText(
      `Veri kaynağı: ${source} veri seti ${run.dataset?.version ?? '?'} (etiketler ${labelState}).`,
      FOOTER_CHARS,
    ),
    ...wrapText(
      `Örnek: ${scope} · Deney tarihi: ${runDate(run)} · Deney: ${run.id} · Kaynak commit: ${(run.source_commit ?? '').slice(0, 7) || UNKNOWN}`,
      FOOTER_CHARS,
    ),
    ...wrapText(
      `Modeller: ${results.map((r) => `${strategyTitle(r.info)} = ${strategyModelLine(r.info)}`).join(' · ')}`,
      FOOTER_CHARS,
    ),
  ]
  if (run.hybrid_routing) {
    footer.push(...wrapText(`Hibrit yönlendirme: ${routingLabel(run.hybrid_routing)}.`, FOOTER_CHARS))
  }
  const codes = detail.warnings.map((w) => w.code)
  if (codes.includes('small_sample')) {
    footer.push(
      ...wrapText(
        'Küçük örneklem: bu görsel bağlantı/biçim doğrulamasıdır; genelleme veya tasarruf sonucu çıkarılamaz.',
        FOOTER_CHARS,
      ),
    )
  }
  if (codes.includes('disputed_labels')) {
    footer.push(
      ...wrapText(
        'Tartışmalı etiketli örnek var (bağımsız ikinci değerlendirme bekliyor); etiketler ve sonuçlar değiştirilmedi.',
        FOOTER_CHARS,
      ),
    )
  }
  footer.push(
    ...wrapText(
      "Token sayıları farklı tokenizer'lar nedeniyle birebir karşılaştırılamaz; ücret sağlayıcının bildirdiği kullanımdan hesaplanır.",
      FOOTER_CHARS,
    ),
  )
  const height = footerTop + 22 + footer.length * 17 + 26

  return {
    headerY,
    scope,
    warn,
    pillWidth,
    colWidth,
    tableTop,
    rows,
    chartTop,
    exampleTop,
    textLines,
    exampleHeight,
    footerTop,
    footer,
    height,
  }
}

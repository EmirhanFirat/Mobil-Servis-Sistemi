import type { ReactNode, Ref } from 'react'

import { FONT, GRID, INK, MUTED, SHARE_WIDTH, costBarItems, latencyPairItems, strategyColor } from '../lib/chart-data'
import type { ExperimentDetail, ExperimentSample, SampleStrategy } from '../lib/experiment-types'
import { UNKNOWN, formatCount, formatUsd, strategyModelLine, strategyTitle } from '../lib/experiments'
import { labelOf } from '../lib/format'
import { wrapText } from '../lib/image-export'
import { ESCALATION_LABEL, LABEL_COL, PAD, computeShareLayout, escalationLines } from '../lib/share-layout'
import type { Vocabulary } from '../lib/types'
import { BarChart, PairedBarChart } from './experiment-charts'

function Lines({
  lines,
  x,
  y,
  size,
  fill = INK,
  weight = 400,
  gap = 1.4,
  anchor,
}: {
  lines: string[]
  x: number
  y: number
  size: number
  fill?: string
  weight?: number
  gap?: number
  anchor?: 'start' | 'middle' | 'end'
}) {
  return (
    <>
      {lines.map((line, index) => (
        <text
          key={`${index}-${line}`}
          x={x}
          y={y + index * size * gap}
          fontFamily={FONT}
          fontSize={size}
          fontWeight={weight}
          fill={fill}
          textAnchor={anchor}
        >
          {line}
        </text>
      ))}
    </>
  )
}

function categoryName(vocab: Vocabulary, code: string | null): string {
  return code === null || code === 'unclear' ? 'Belirsiz' : labelOf(vocab.categories, code)
}

function priorityName(vocab: Vocabulary, code: string | null): string {
  return code === null ? 'Belirsiz' : labelOf(vocab.priorities, code)
}

function verdict(ok: boolean | null): { text: string; color: string } {
  if (ok === null) return { text: '', color: MUTED }
  return ok ? { text: ' (doğru)', color: '#047857' } : { text: ' (yanlış)', color: '#b91c1c' }
}

function ExampleColumn({
  x,
  y,
  strategy,
  vocab,
  color,
}: {
  x: number
  y: number
  strategy: SampleStrategy
  vocab: Vocabulary
  color: string
}) {
  const cat = verdict(strategy.category_ok)
  const pri = verdict(strategy.priority_ok)
  const row = (index: number, label: string, value: string, extra?: { text: string; color: string }) => (
    <text key={label} x={x} y={y + 46 + index * 24} fontFamily={FONT} fontSize={14} fill={INK}>
      <tspan fill={MUTED}>{label}: </tspan>
      {value}
      {extra && extra.text ? <tspan fill={extra.color}>{extra.text}</tspan> : null}
    </text>
  )
  if (!strategy.present || strategy.failed) {
    return (
      <g>
        <text x={x} y={y + 18} fontFamily={FONT} fontSize={17} fontWeight={700} fill={color}>
          {strategyTitle(strategy.info)}
        </text>
        <text x={x} y={y + 46} fontFamily={FONT} fontSize={14} fill="#b91c1c">
          {strategy.present ? 'Karar üretilemedi' : 'Bu örnekte kayıt yok'}
        </text>
      </g>
    )
  }
  const escalation = escalationLines(strategy)
  return (
    <g>
      <text x={x} y={y + 18} fontFamily={FONT} fontSize={17} fontWeight={700} fill={color}>
        {strategyTitle(strategy.info)}
      </text>
      {row(0, 'Kategori', categoryName(vocab, strategy.category), cat)}
      {row(1, 'Öncelik', priorityName(vocab, strategy.priority), pri)}
      {row(2, 'İnceleme', strategy.review_required ? 'gerekiyor' : 'gerekmiyor')}
      {row(3, 'Süre', strategy.latency_ms === null ? UNKNOWN : `${formatCount(strategy.latency_ms)} ms`)}
      {row(
        4,
        'Ücret',
        strategy.calls_with_unknown_cost
          ? `${formatUsd(strategy.cost_known_usd)} + bilinmeyen`
          : formatUsd(strategy.cost_known_usd),
      )}
      {escalation.map((line, index) => (
        <text
          key={`${index}-${line}`}
          x={x}
          y={y + 46 + 5 * 24 + index * 14 * 1.4}
          fontFamily={FONT}
          fontSize={14}
          fill={INK}
        >
          {index === 0 && line.startsWith(ESCALATION_LABEL) ? (
            <>
              <tspan fill={MUTED}>{ESCALATION_LABEL}</tspan>
              {line.slice(ESCALATION_LABEL.length)}
            </>
          ) : (
            line
          )}
        </text>
      ))}
    </g>
  )
}

interface Props {
  detail: ExperimentDetail
  example: ExperimentSample | null
  vocab: Vocabulary
  svgRef?: Ref<SVGSVGElement>
}

export default function ShareCard({ detail, example, vocab, svgRef }: Props) {
  const results = detail.strategies
  const layout = computeShareLayout(detail, example)
  const { headerY, scope, warn, pillWidth, colWidth, tableTop, chartTop, exampleTop } = layout
  const { textLines, exampleHeight, footerTop, footer, height } = layout

  const exampleColumns = example ? example.strategies : []
  const colX = 480
  const exampleColWidth = (SHARE_WIDTH - PAD - colX) / Math.max(exampleColumns.length, 1)

  const body: ReactNode[] = layout.rows.map(({ row, labelLines, wrapped, height: h, top }, rowIndex) => {
    return (
      <g key={row.key}>
        {rowIndex % 2 === 0 ? <rect x={PAD} y={top} width={SHARE_WIDTH - 2 * PAD} height={h} fill="#f8fafc" /> : null}
        <Lines lines={labelLines} x={PAD + 10} y={top + 22} size={15} weight={600} gap={1.25} />
        {results.map((r, index) => (
          <Lines
            key={r.name}
            lines={wrapped[index]}
            x={PAD + LABEL_COL + colWidth * index + 10}
            y={top + 22}
            size={15}
            gap={1.25}
          />
        ))}
      </g>
    )
  })

  return (
    <svg
      ref={svgRef}
      xmlns="http://www.w3.org/2000/svg"
      width={SHARE_WIDTH}
      height={height}
      viewBox={`0 0 ${SHARE_WIDTH} ${height}`}
      style={{ maxWidth: '100%', height: 'auto', display: 'block' }}
      role="img"
      aria-label="Jev, LLM ve hibrit karşılaştırması: paylaşım görünümü"
      data-testid="share-card"
    >
      <title>Jev, LLM ve hibrit karşılaştırması</title>
      <rect x={0} y={0} width={SHARE_WIDTH} height={height} fill="#ffffff" />
      <rect x={1} y={1} width={SHARE_WIDTH - 2} height={height - 2} fill="none" stroke={GRID} strokeWidth={2} />

      <text x={PAD} y={headerY + 30} fontFamily={FONT} fontSize={30} fontWeight={800} fill={INK}>
        Jev, LLM ve hibrit: Türkçe servis taleplerinde karar karşılaştırması
      </text>
      <text x={PAD} y={headerY + 58} fontFamily={FONT} fontSize={16} fill={MUTED}>
        TalepAkış · kayıtlı deney dosyalarından hesaplanan gerçek ölçümler
      </text>
      <rect
        x={PAD}
        y={headerY + 70}
        width={pillWidth}
        height={32}
        rx={16}
        fill={warn ? '#fef3c7' : '#e6f6ee'}
        stroke={warn ? '#d97706' : '#047857'}
      />
      <text
        x={PAD + 18}
        y={headerY + 92}
        fontFamily={FONT}
        fontSize={16}
        fontWeight={700}
        fill={warn ? '#92400e' : '#065f46'}
      >
        {scope}
      </text>

      <rect x={PAD} y={tableTop} width={SHARE_WIDTH - 2 * PAD} height={58} fill="#eef2f7" />
      <text x={PAD + 10} y={tableTop + 35} fontFamily={FONT} fontSize={14} fontWeight={700} fill={MUTED}>
        ÖLÇÜT
      </text>
      {results.map((r, index) => {
        const x = PAD + LABEL_COL + colWidth * index + 10
        return (
          <g key={r.name}>
            <text
              x={x}
              y={tableTop + 26}
              fontFamily={FONT}
              fontSize={20}
              fontWeight={800}
              fill={strategyColor(r.info.kind, index)}
            >
              {strategyTitle(r.info)}
            </text>
            <Lines
              lines={wrapText(strategyModelLine(r.info), 38, 2)}
              x={x}
              y={tableTop + 43}
              size={11}
              fill={MUTED}
              gap={1.2}
            />
          </g>
        )
      })}
      {body}

      <BarChart
        x={PAD}
        y={chartTop}
        width={520}
        height={262}
        title="Tamamlanan talep başına ölçülen ücret"
        subtitle="USD · yalnızca ücret (gecikmeyle aynı eksende değil)"
        items={costBarItems(results)}
      />
      <PairedBarChart
        x={PAD + 560}
        y={chartTop}
        width={560}
        height={262}
        title="Uçtan uca karar süresi"
        subtitle="milisaniye · ağ ve yeniden deneme dahil"
        firstLabel="p50"
        secondLabel="p95"
        items={latencyPairItems(results)}
      />

      <text x={PAD} y={exampleTop + 24} fontFamily={FONT} fontSize={20} fontWeight={800} fill={INK}>
        Örnek talep karşılaştırması
        {example ? ` · ${example.sample.id}` : ''}
      </text>
      {example ? (
        <g>
          <rect
            x={PAD}
            y={exampleTop + 38}
            width={SHARE_WIDTH - 2 * PAD}
            height={exampleHeight}
            rx={10}
            fill="#f8fafc"
            stroke={GRID}
          />
          <Lines lines={textLines} x={PAD + 18} y={exampleTop + 70} size={15} gap={1.4} />
          <text
            x={PAD + 18}
            y={exampleTop + 70 + textLines.length * 21 + 14}
            fontFamily={FONT}
            fontSize={14}
            fontWeight={700}
            fill={INK}
          >
            {`Beklenen etiket: ${categoryName(vocab, example.sample.gold.category)} · ${priorityName(vocab, example.sample.gold.priority)}`}
          </text>
          {example.sample.disputed ? (
            <text
              x={PAD + 18}
              y={exampleTop + 70 + textLines.length * 21 + 36}
              fontFamily={FONT}
              fontSize={13}
              fontWeight={700}
              fill="#92400e"
            >
              Tartışmalı etiket (ikinci değerlendirme bekliyor)
            </text>
          ) : null}
          {exampleColumns.map((strategy, index) => (
            <ExampleColumn
              key={strategy.name}
              x={colX + exampleColWidth * index}
              y={exampleTop + 52}
              strategy={strategy}
              vocab={vocab}
              color={strategyColor(strategy.info.kind, index)}
            />
          ))}
        </g>
      ) : (
        <text x={PAD} y={exampleTop + 58} fontFamily={FONT} fontSize={15} fill={MUTED}>
          Örnek talep seçilmedi.
        </text>
      )}

      <line x1={PAD} x2={SHARE_WIDTH - PAD} y1={footerTop} y2={footerTop} stroke={GRID} strokeWidth={1.5} />
      <Lines lines={footer} x={PAD} y={footerTop + 22} size={12} fill={MUTED} gap={1.4} />
    </svg>
  )
}

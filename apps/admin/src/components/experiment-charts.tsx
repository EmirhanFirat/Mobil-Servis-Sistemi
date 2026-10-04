import type { ReactNode } from 'react'

import { type BarItem, type PairItem, FONT, GRID, INK, MUTED, barPixels } from '../lib/chart-data'
import { UNKNOWN } from '../lib/experiments'

/**
 * Basit çubuk grafikler (ek bağımlılık yok). Tüm öznitelikler SATIR İÇİDİR (CSS sınıfı yok): aynı SVG
 * hem ekranda gösterilir hem PNG'ye çevrilir. Ücret ve gecikme AYRI grafiklerdir; farklı birimler
 * aynı eksende karıştırılmaz. Bilinmeyen değer çubuk çizilmez, "bilinmiyor" yazılır (sıfır değil).
 */

interface Frame {
  x: number
  y: number
  width: number
  height: number
  title: string
  subtitle?: string
}

function Header({ x, y, title, subtitle }: Pick<Frame, 'x' | 'y' | 'title' | 'subtitle'>) {
  return (
    <>
      <text x={x} y={y + 20} fontFamily={FONT} fontSize={18} fontWeight={700} fill={INK}>
        {title}
      </text>
      {subtitle ? (
        <text x={x} y={y + 40} fontFamily={FONT} fontSize={13} fill={MUTED}>
          {subtitle}
        </text>
      ) : null}
    </>
  )
}

export function BarChart({ items, x, y, width, height, title, subtitle }: Frame & { items: BarItem[] }) {
  const top = y + 62
  const baseline = y + height - 34
  const plot = baseline - top
  const values = items.map((item) => item.value ?? 0)
  const max = Math.max(...values, 0)
  const slot = width / Math.max(items.length, 1)
  const barWidth = Math.min(96, slot * 0.55)

  return (
    <g role="img" aria-label={title}>
      <Header x={x} y={y} title={title} subtitle={subtitle} />
      <line x1={x} x2={x + width} y1={baseline} y2={baseline} stroke={GRID} strokeWidth={1.5} />
      {items.map((item, index) => {
        const cx = x + slot * index + slot / 2
        const known = item.value !== null
        const barHeight = barPixels(item.value, max, plot)
        return (
          <g key={item.key}>
            {known ? (
              <rect
                x={cx - barWidth / 2}
                y={baseline - barHeight}
                width={barWidth}
                height={barHeight}
                rx={4}
                fill={item.color}
              />
            ) : null}
            <text
              x={cx}
              y={known ? baseline - barHeight - 8 : baseline - 12}
              textAnchor="middle"
              fontFamily={FONT}
              fontSize={15}
              fontWeight={700}
              fill={known ? INK : MUTED}
            >
              {known ? item.text : UNKNOWN}
            </text>
            <text
              x={cx}
              y={baseline + 22}
              textAnchor="middle"
              fontFamily={FONT}
              fontSize={15}
              fontWeight={600}
              fill={INK}
            >
              {item.label}
            </text>
          </g>
        )
      })}
    </g>
  )
}

/** Her strateji için iki çubuk (ör. p50 ve p95): aynı birim, aynı eksen. */
export function PairedBarChart({
  items,
  x,
  y,
  width,
  height,
  title,
  subtitle,
  firstLabel,
  secondLabel,
}: Frame & { items: PairItem[]; firstLabel: string; secondLabel: string }) {
  const top = y + 62
  const baseline = y + height - 34
  const plot = baseline - top
  const max = Math.max(...items.flatMap((item) => [item.first ?? 0, item.second ?? 0]), 0)
  const slot = width / Math.max(items.length, 1)
  const barWidth = Math.min(54, slot * 0.28)

  const bar = (value: number | null, cx: number, color: string, opacity: number) => {
    const h = barPixels(value, max, plot)
    if (h === 0) return null
    return (
      <rect x={cx - barWidth / 2} y={baseline - h} width={barWidth} height={h} rx={4} fill={color} opacity={opacity} />
    )
  }

  return (
    <g role="img" aria-label={title}>
      <Header x={x} y={y} title={title} subtitle={subtitle} />
      <rect x={x + width - 170} y={y + 6} width={12} height={12} rx={2} fill={MUTED} />
      <text x={x + width - 152} y={y + 17} fontFamily={FONT} fontSize={13} fill={INK}>
        {firstLabel}
      </text>
      <rect x={x + width - 96} y={y + 6} width={12} height={12} rx={2} fill={MUTED} opacity={0.4} />
      <text x={x + width - 78} y={y + 17} fontFamily={FONT} fontSize={13} fill={INK}>
        {secondLabel}
      </text>
      <line x1={x} x2={x + width} y1={baseline} y2={baseline} stroke={GRID} strokeWidth={1.5} />
      {items.map((item, index) => {
        const cx = x + slot * index + slot / 2
        const left = cx - barWidth * 0.62
        const right = cx + barWidth * 0.62
        const h1 = barPixels(item.first, max, plot)
        const h2 = barPixels(item.second, max, plot)
        return (
          <g key={item.key}>
            {bar(item.first, left, item.color, 1)}
            {bar(item.second, right, item.color, 0.4)}
            <text
              x={left}
              y={baseline - h1 - 7}
              textAnchor="middle"
              fontFamily={FONT}
              fontSize={13}
              fontWeight={700}
              fill={item.first === null ? MUTED : INK}
            >
              {item.first === null ? UNKNOWN : item.firstText}
            </text>
            <text
              x={right}
              y={baseline - h2 - 7}
              textAnchor="middle"
              fontFamily={FONT}
              fontSize={13}
              fontWeight={700}
              fill={item.second === null ? MUTED : INK}
            >
              {item.second === null ? UNKNOWN : item.secondText}
            </text>
            <text
              x={cx}
              y={baseline + 22}
              textAnchor="middle"
              fontFamily={FONT}
              fontSize={15}
              fontWeight={600}
              fill={INK}
            >
              {item.label}
            </text>
          </g>
        )
      })}
    </g>
  )
}

/** Bir grafiği kendi SVG'siyle sarar (ana ekranda). */
export function ChartSvg({
  width,
  height,
  label,
  children,
}: {
  width: number
  height: number
  label: string
  children: ReactNode
}) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      style={{ maxWidth: width, height: 'auto' }}
      role="img"
      aria-label={label}
    >
      {children}
    </svg>
  )
}

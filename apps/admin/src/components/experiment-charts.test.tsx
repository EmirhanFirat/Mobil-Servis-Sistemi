import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { BarItem, PairItem } from '../lib/chart-data'
import { BarChart, PairedBarChart } from './experiment-charts'

const frame = { x: 0, y: 0, width: 400, height: 260, title: 'Başlık' }

function bars(container: HTMLElement): number {
  return container.querySelectorAll('rect').length
}

describe('BarChart', () => {
  it('bilinmeyen değer için çubuk çizmez ve "bilinmiyor" yazar (metin sıfır olsa bile)', () => {
    const items: BarItem[] = [
      { key: 'a', label: 'Bilinen', value: 0.5, text: '0,5', color: '#111' },
      { key: 'b', label: 'Bilinmeyen', value: null, text: '0,0000', color: '#222' },
    ]
    const { container } = render(
      <svg>
        <BarChart {...frame} items={items} />
      </svg>,
    )

    expect(bars(container)).toBe(1)
    expect(screen.getByText('bilinmiyor')).toBeInTheDocument()
    expect(screen.queryByText('0,0000')).not.toBeInTheDocument()
  })

  it('çok küçük ama pozitif değer görünür kalır (en az 3 piksel)', () => {
    const items: BarItem[] = [
      { key: 'a', label: 'Büyük', value: 1000, text: '1000', color: '#111' },
      { key: 'b', label: 'Küçük', value: 0.001, text: '0,001', color: '#222' },
    ]
    const { container } = render(
      <svg>
        <BarChart {...frame} items={items} />
      </svg>,
    )

    const heights = Array.from(container.querySelectorAll('rect')).map((r) => Number(r.getAttribute('height')))
    expect(heights).toHaveLength(2)
    expect(Math.min(...heights)).toBeGreaterThanOrEqual(3)
    expect(Math.max(...heights)).toBeGreaterThan(100)
  })

  it('tüm değerler bilinmiyorsa hiç çubuk yoktur', () => {
    const items: BarItem[] = [{ key: 'a', label: 'A', value: null, text: 'x', color: '#111' }]
    const { container } = render(
      <svg>
        <BarChart {...frame} items={items} />
      </svg>,
    )

    expect(bars(container)).toBe(0)
  })
})

describe('PairedBarChart', () => {
  const frame2 = { ...frame, firstLabel: 'p50', secondLabel: 'p95' }

  it('her strateji için iki çubuk; bilinmeyen süre "bilinmiyor"', () => {
    const items: PairItem[] = [
      { key: 'a', label: 'A', first: 300, firstText: '300', second: 400, secondText: '400', color: '#111' },
      { key: 'b', label: 'B', first: null, firstText: '0', second: null, secondText: '0', color: '#222' },
    ]
    const { container } = render(
      <svg>
        <PairedBarChart {...frame2} items={items} />
      </svg>,
    )

    // 2 gösterge kutusu + A için 2 çubuk (B bilinmiyor)
    expect(bars(container)).toBe(2 + 2)
    expect(screen.getAllByText('bilinmiyor')).toHaveLength(2)
    expect(screen.getByText('p50')).toBeInTheDocument()
    expect(screen.getByText('p95')).toBeInTheDocument()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'

import { downloadText, serializeSvg, wrapText } from './image-export'

describe('wrapText', () => {
  it('kelimeleri bölmeden satırlara ayırır', () => {
    expect(wrapText('Asansör kapısı kapanmıyor kata gelince açılmıyor', 20)).toEqual([
      'Asansör kapısı',
      'kapanmıyor kata',
      'gelince açılmıyor',
    ])
  })

  it('satır genişliğini aşan tek kelimeyi böler', () => {
    expect(wrapText('abcdefghij', 4)).toEqual(['abcd', 'efgh', 'ij'])
  })

  it('en çok satır sayısını aşınca sonuncuyu üç noktayla keser', () => {
    const lines = wrapText('bir iki üç dört beş altı yedi sekiz', 8, 2)

    expect(lines).toHaveLength(2)
    expect(lines[1].endsWith('…')).toBe(true)
    expect(lines[1].length).toBeLessThanOrEqual(8)
  })

  it('boş ve yalnızca boşluk içeren metinde satır üretmez; ardışık boşluğu tek sayar', () => {
    expect(wrapText('', 10)).toEqual([])
    expect(wrapText('   ', 10)).toEqual([])
    expect(wrapText('a    b', 10)).toEqual(['a b'])
  })

  it('metindeki hiçbir karakteri kaybetmez (kesme yoksa)', () => {
    const text = 'lavabodan sürekli su akıyor yer su oldu yardım edin lütfen acil'
    expect(wrapText(text, 15).join(' ')).toBe(text)
  })
})

describe('serializeSvg', () => {
  it('xmlns ekler, özgün öğeyi değiştirmez', () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg') as SVGSVGElement
    svg.setAttribute('width', '10')

    const markup = serializeSvg(svg)

    expect(markup).toContain('xmlns="http://www.w3.org/2000/svg"')
    expect(markup).toContain('width="10"')
    expect(svg.getAttribute('xmlns')).toBeNull()
  })
})

describe('downloadText', () => {
  afterEach(() => vi.restoreAllMocks())

  it('verilen adla, UTF-8 ve doğru türle indirir', async () => {
    const created: Blob[] = []
    URL.createObjectURL = vi.fn((blob: Blob) => {
      created.push(blob)
      return 'blob:test'
    })
    URL.revokeObjectURL = vi.fn()
    const clicked: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download)
    })

    downloadText('çğüşöı', 'dosya.csv', 'text/csv')

    expect(clicked).toEqual(['dosya.csv'])
    expect(created[0].type).toBe('text/csv;charset=utf-8')
    expect(await created[0].text()).toBe('çğüşöı')
    expect(document.querySelector('a[download]')).toBeNull() // bağlantı DOM'dan kaldırıldı
  })
})

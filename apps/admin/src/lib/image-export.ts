/** SVG'yi (paylaşım kartı) PNG'ye çevirme ve dosya indirme. Ek bağımlılık yoktur: tarayıcının canvas'ı. */

/** Satırlara bölünmüş metin: kelimeleri korur, `maxChars`'ı aşan tek kelimeyi böler. */
export function wrapText(text: string, maxChars: number, maxLines = Infinity): string[] {
  const lines: string[] = []
  let current = ''
  const push = (line: string) => {
    if (line) lines.push(line)
  }
  for (const rawWord of text.replace(/\s+/g, ' ').trim().split(' ')) {
    let word = rawWord
    while (word.length > maxChars) {
      push(current)
      current = ''
      push(word.slice(0, maxChars))
      word = word.slice(maxChars)
    }
    if (!current) current = word
    else if (current.length + 1 + word.length <= maxChars) current += ` ${word}`
    else {
      push(current)
      current = word
    }
  }
  push(current)
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines)
    kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, Math.max(0, maxChars - 1))}…`
    return kept
  }
  return lines
}

/** İşaretlemeyi bağımsız bir SVG belgesi olarak serileştirir (stil sınıfı olmadan; tüm öznitelikler satır içi). */
export function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  return new XMLSerializer().serializeToString(clone)
}

/** SVG'yi `scale` katı çözünürlükte PNG blob'una çevirir. Arka plan beyaz doldurulur. */
export async function svgToPngBlob(svg: SVGSVGElement, scale = 2): Promise<Blob> {
  const width = Number(svg.getAttribute('width'))
  const height = Number(svg.getAttribute('height'))
  if (!width || !height) throw new Error('Görselin boyutu bilinmiyor.')

  const url = URL.createObjectURL(new Blob([serializeSvg(svg)], { type: 'image/svg+xml;charset=utf-8' }))
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('Görsel oluşturulamadı.'))
      image.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(width * scale)
    canvas.height = Math.round(height * scale)
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Tarayıcı görsel üretemiyor.')
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG üretilemedi.'))), 'image/png'),
    )
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function downloadText(text: string, filename: string, mime: string): void {
  downloadBlob(new Blob([text], { type: `${mime};charset=utf-8` }), filename)
}

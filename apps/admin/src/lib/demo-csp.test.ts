import { describe, expect, it } from 'vitest'

import { apiOrigin, buildDemoCsp, demoCspPlugin, injectDemoHead } from '../../csp'

const HTML = `<!doctype html>
<html lang="tr">
  <head>
    <meta charset="UTF-8" />
    <title>TalepAkış Yönetim</title>
  </head>
  <body></body>
</html>`

describe('buildDemoCsp', () => {
  it('betik yalnızca kendi kaynağımızdan; satır içi betik ve eval yok', () => {
    const csp = buildDemoCsp('https://api.ornek.com')

    expect(csp).toContain("script-src 'self'")
    expect(csp).not.toMatch(/script-src[^;]*unsafe/)
    expect(csp).toContain("default-src 'self'")
    expect(csp).toContain("object-src 'none'")
    expect(csp).toContain("base-uri 'none'")
    expect(csp).toContain("form-action 'none'")
  })

  it("'unsafe-inline' yalnızca stilde (satır içi style öznitelikleri için)", () => {
    const csp = buildDemoCsp('https://api.ornek.com')

    expect(csp).toContain("style-src 'self' 'unsafe-inline'")
    expect(csp.match(/unsafe-inline/g)).toHaveLength(1)
  })

  it('ağ bağlantısı yalnızca kendi kaynağımıza ve API kaynağına izinlidir', () => {
    const csp = buildDemoCsp('https://talepakis-api.onrender.com/yol/olsa/da')

    expect(csp).toContain("connect-src 'self' https://talepakis-api.onrender.com;")
    expect(csp).not.toContain('/yol/olsa/da')
    expect(csp).not.toContain('*')
  })

  it('API adresi verilmezse geliştirme varsayılanı; geçersiz/yanlış şemada eklenmez', () => {
    expect(buildDemoCsp(undefined)).toContain("connect-src 'self' http://127.0.0.1:8000")
    expect(buildDemoCsp('javascript:alert(1)')).toContain("connect-src 'self';")
    expect(buildDemoCsp('bu bir adres değil')).toContain("connect-src 'self';")
  })

  it('görseller yalnızca kendi kaynağımızdan, data: ve blob: (PNG dışa aktarım) ile', () => {
    expect(buildDemoCsp('https://a.com')).toContain("img-src 'self' data: blob:")
  })
})

describe('apiOrigin', () => {
  it.each([
    ['https://a.onrender.com/x?y=1', 'https://a.onrender.com'],
    ['http://localhost:8000', 'http://localhost:8000'],
    ['ftp://a.com', null],
    ['', 'http://127.0.0.1:8000'],
    [undefined, 'http://127.0.0.1:8000'],
  ])('%s → %s', (input, expected) => {
    expect(apiOrigin(input)).toBe(expected)
  })
})

describe('injectDemoHead', () => {
  it('CSP meta etiketini ve demo başlığını ekler; tırnaklar kaçışlanır', () => {
    const html = injectDemoHead(HTML, `default-src 'self'; connect-src "x"`)

    expect(html).toContain('<meta http-equiv="Content-Security-Policy"')
    expect(html).toContain('&quot;x&quot;')
    expect(html).toContain('<title>TalepAkış — canlı demo</title>')
    expect(html).not.toContain('TalepAkış Yönetim')
    expect(html.indexOf('Content-Security-Policy')).toBeLessThan(html.indexOf('<title>'))
  })

  it('eklenti yalnızca derlemede çalışır ve index.html dönüştürür', () => {
    const plugin = demoCspPlugin('https://api.ornek.com')
    const transform = plugin.transformIndexHtml as (html: string) => string

    expect(plugin.apply).toBe('build')
    expect(transform(HTML)).toContain('connect-src')
  })
})

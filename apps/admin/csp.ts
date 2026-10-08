import type { Plugin } from 'vite'

/**
 * Herkese açık demo derlemesi için İçerik Güvenlik Politikası (CSP). Statik barındırıcıda yanıt
 * başlığı ayarlamak platforma bağlıdır; bu yüzden politika derleme sırasında `index.html`e
 * `<meta http-equiv>` olarak gömülür (her barındırıcıda çalışır). Not: `frame-ancestors` meta
 * etiketiyle uygulanamaz; çerçevelenme koruması için barındırıcıda `X-Frame-Options` başlığı da
 * (isteğe bağlı) tanımlanır (docs/DEPLOY.md).
 *
 * - Betik yalnızca kendi kaynağımızdan; satır içi betik YOK.
 * - Stil: satır içi `style` öznitelikleri (React ve SVG kartı) için 'unsafe-inline' yalnızca stilde.
 * - Ağ: yalnızca kendi kaynağımız ve API'nin kaynağı (statik sonuç dosyaları aynı kaynaktadır).
 */
export function buildDemoCsp(apiUrl: string | undefined): string {
  const connect = ["'self'"]
  const origin = apiOrigin(apiUrl)
  if (origin) connect.push(origin)
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connect.join(' ')}`,
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'",
  ].join('; ')
}

/** `https://api.ornek.com/yol` → `https://api.ornek.com`. Geçersizse null (CSP'ye eklenmez). */
export function apiOrigin(apiUrl: string | undefined): string | null {
  if (!apiUrl) return 'http://127.0.0.1:8000' // geliştirme varsayılanı (lib/config.ts ile aynı)
  try {
    const url = new URL(apiUrl)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null
  } catch {
    return null
  }
}

export function injectDemoHead(html: string, csp: string): string {
  const escaped = csp.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
  const meta = `<meta http-equiv="Content-Security-Policy" content="${escaped}" />`
  const description =
    '<meta name="description" content="TalepAkış canlı demo: Türkçe servis taleplerinde gerçek Jev ile karar üretimi ve kayıtlı ölçüm sonuçları." />'
  return html
    .replace('<title>TalepAkış Yönetim</title>', '<title>TalepAkış — canlı demo</title>')
    .replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" />\n    ${meta}\n    ${description}`)
}

export function demoCspPlugin(apiUrl: string | undefined): Plugin {
  return {
    name: 'talepakis-demo-csp',
    apply: 'build',
    transformIndexHtml: (html) => injectDemoHead(html, buildDemoCsp(apiUrl)),
  }
}

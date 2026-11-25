import { durationText } from '../lib/demo-text'
import { WAKE_ATTEMPTS, WAKE_PAUSE_MS, type WakeState } from './use-wake-up'

const SLEEP_NOTE =
  'Ücretsiz barındırma kullanıyoruz: sunucu boştayken uyur ve ilk açılış yaklaşık 1 dakika sürebilir. Bu istek model çağrısı yapmaz.'

/**
 * Sunucunun hazırlık durumu: küçük bir rozet. Uyanırken ilerleme göstergesi görünür kalır; hazır
 * olunca ayrıntı (uyanma süresi) rozetin içinde katlanır. Bu istekler model çağrısı yapmaz.
 */
export default function WakePanel({ state }: { state: WakeState }) {
  if (state.phase === 'checking' || state.phase === 'waiting') {
    const text =
      state.phase === 'checking'
        ? `Sunucu hazırlanıyor… (deneme ${state.attempt}/${WAKE_ATTEMPTS})`
        : `Sunucu uyanıyor; ${Math.round(WAKE_PAUSE_MS / 1000)} sn sonra yeniden denenecek (deneme ${state.attempt}/${WAKE_ATTEMPTS})`
    return (
      <div className="server-status waking" role="status" aria-live="polite" title={SLEEP_NOTE}>
        <span className="spinner spinner-small" aria-hidden="true" />
        <span>
          {text}
          <span className="visually-hidden"> {SLEEP_NOTE}</span>
        </span>
      </div>
    )
  }
  if (state.phase === 'failed') {
    return (
      <span className="server-status down" role="status">
        <span className="dot" aria-hidden="true" /> Sunucuya ulaşılamadı
      </span>
    )
  }
  const detail =
    `İlk istekten hazır olana kadar geçen süre: ${durationText(state.wakeMs)}` +
    (state.status.database_ms !== null ? ` (bunun veritabanı kısmı: ${durationText(state.status.database_ms)})` : '') +
    '. Bu süre ücretsiz sunucunun/veritabanının uyanmasını içerir; Jev çağrı süresi değildir.'
  return (
    <details className="server-status ready" data-testid="wake-summary" title={detail}>
      <summary>
        <span className="dot" aria-hidden="true" /> Sunucu hazır
      </summary>
      <p className="small muted">{detail}</p>
    </details>
  )
}

/** Denemeler tükendi: gerçek bir bağlantı sorunu; kullanıcı kontrollü yeniden deneme. */
export function WakeFailed({ state, onRetry }: { state: Extract<WakeState, { phase: 'failed' }>; onRetry: () => void }) {
  return (
    <div className="state compact" role="alert">
      <h3>Sunucu şu an yanıt vermedi</h3>
      <p className="muted">
        {WAKE_ATTEMPTS} deneme sonuçsuz kaldı ({state.error.message}). Ücretsiz sunucunun uyanması bazen daha uzun
        sürer. Hazır olduğunda yeniden deneyebilirsin; sayfa kendiliğinden sürekli denemez.
      </p>
      <button type="button" className="btn btn-primary" onClick={onRetry}>
        Yeniden dene
      </button>
    </div>
  )
}

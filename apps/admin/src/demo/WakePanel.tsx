import { Loading, Notice } from '../components/ui'
import { durationText, unavailableText } from '../lib/demo-text'
import { WAKE_ATTEMPTS, WAKE_PAUSE_MS, type WakeState } from './use-wake-up'

/** Sunucunun hazırlık durumu. Bu istekler model çağrısı yapmaz. */
export default function WakePanel({ state, onRetry }: { state: WakeState; onRetry: () => void }) {
  if (state.phase === 'checking') {
    return (
      <Loading
        message={
          `Sunucu hazırlanıyor… (deneme ${state.attempt}/${WAKE_ATTEMPTS}). Ücretsiz barındırma kullanıyoruz: ` +
          'sunucu boştayken uyur ve ilk açılış yaklaşık 1 dakika sürebilir. Bu istek model çağrısı yapmaz.'
        }
      />
    )
  }
  if (state.phase === 'waiting') {
    return (
      <Notice tone="info">
        Sunucu henüz hazır değil (deneme {state.attempt}/{WAKE_ATTEMPTS}); yaklaşık {Math.round(WAKE_PAUSE_MS / 1000)}{' '}
        sn sonra yeniden denenecek. Ücretsiz sunucu uyanıyor olabilir; biraz beklemen yeterli.
      </Notice>
    )
  }
  if (state.phase === 'failed') {
    return (
      <div className="state" role="alert">
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
  const reason = unavailableText(state.status)
  return (
    <div className="stack">
      {reason ? <Notice tone="error">{reason}</Notice> : null}
      <p className="small muted" data-testid="wake-summary">
        Sunucu hazır. İlk istekten hazır olana kadar geçen süre: <strong>{durationText(state.wakeMs)}</strong>
        {state.status.database_ms !== null ? (
          <> (bunun veritabanı kısmı: {durationText(state.status.database_ms)})</>
        ) : null}
        . Bu süre ücretsiz sunucunun/veritabanının uyanmasını içerir; Jev çağrı süresi değildir.
      </p>
    </div>
  )
}

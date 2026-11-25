import { useEffect, useRef } from 'react'

import { Badge } from '../components/ui'
import { formatDateTime, labelOf, ticketNumber } from '../lib/format'
import type { Vocabulary } from '../lib/types'
import type { Topic } from './portal-topics'
import ResultPanel from './ResultPanel'
import type { DecisionRun } from './use-demo-decision'

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true" focusable="false">
      <path
        d="m5 12.5 4.5 4.5L19 7.5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/** Karşılayan motor: arayüz her zaman açıkça yazar; kural tabanlı karşılama "yapay zekâ" sayılmaz. */
function EngineBadge({ run }: { run: DecisionRun }) {
  const { result } = run
  if (result.engine === 'rules') return <Badge kind="source-rule">Kural tabanlı ön değerlendirme</Badge>
  if (result.decision?.is_mock) return <Badge kind="source-mock">MOCK — gerçek model değil</Badge>
  if (result.engine === 'jev') return <Badge kind="source-real">Yapay zekâ ön değerlendirmesi · Jev</Badge>
  return null
}

/**
 * Talep fişi: talep numarası, durum ve (karar varsa) kategori, öncelik, yönlendirilen ekip.
 * Değerler yalnızca sunucu yanıtından gelir; karar yoksa alan boş bırakılır, tahmin edilmez.
 */
export default function Receipt({
  run,
  vocab,
  topic,
  wakeMs,
  busy,
  onCheck,
  onResend,
  onNew,
}: {
  run: DecisionRun
  vocab: Vocabulary | null
  /** Ziyaretçinin formda seçtiği konu (karara girdi değildir; yalnızca karşılaştırma). */
  topic: Topic | null
  wakeMs: number | null
  busy: boolean
  onCheck: (ticketId: string) => void
  onResend: () => void
  onNew: () => void
}) {
  const { result } = run
  const info = result.decision
  const ref = useRef<HTMLElement>(null)
  // Gönderim düğmesi (özellikle mobilde) sayfanın altındadır; fiş açılınca başı görünsün.
  useEffect(() => {
    const element = ref.current
    if (element && typeof element.scrollIntoView === 'function') {
      element.scrollIntoView({ block: 'start', behavior: 'smooth' })
    }
  }, [result.ticket_id])
  const done = result.state === 'completed'
  const waiting = result.state === 'pending' || result.state === 'running'
  const routed = done && result.team !== null
  const category = info?.category ? labelOf(vocab?.categories ?? [], info.category) : null
  const priority = info?.priority ? labelOf(vocab?.priorities ?? [], info.priority) : null
  const team = result.team ? labelOf(vocab?.teams ?? [], result.team) : null
  const missing = (info?.missing_info ?? []).map((code) => labelOf(vocab?.missing_info ?? [], code))
  const title = routed ? 'Talebin alındı ve ilgili ekibe yönlendirildi' : 'Talebin kaydedildi'
  const showMessage = !(done && result.engine === 'jev')

  return (
    <section ref={ref} className="receipt card" aria-label="Talep fişi" aria-live="polite">
      <div className="receipt-head">
        <span className={`receipt-icon ${routed ? 'ok' : 'wait'}`}>{routed ? <CheckIcon /> : <ClockIcon />}</span>
        <div className="receipt-title">
          <h2>{title}</h2>
          <p className="muted small">
            Talep numaran <strong className="ticket-no">{ticketNumber(result.ticket_number)}</strong> ·{' '}
            {formatDateTime(result.created_at)}
          </p>
        </div>
        <EngineBadge run={run} />
      </div>

      {showMessage ? <p className={`receipt-message ${done ? 'muted' : ''}`}>{result.message}</p> : null}

      <dl className="receipt-grid">
        <div>
          <dt>Durum</dt>
          <dd>{labelOf(vocab?.statuses ?? [], result.ticket_status)}</dd>
        </div>
        <div>
          <dt>Kategori</dt>
          <dd>{category ?? (done ? 'Belirsiz' : '—')}</dd>
        </div>
        <div>
          <dt>Öncelik</dt>
          <dd>
            {priority ? (
              <Badge kind={info?.priority === 'high' ? 'priority-high' : undefined}>{priority}</Badge>
            ) : done ? (
              'Belirsiz'
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div>
          <dt>Yönlendirilen ekip</dt>
          <dd>{team ?? (done ? 'İnsan incelemesine bırakıldı' : '—')}</dd>
        </div>
      </dl>

      {topic?.category && done ? (
        <p className="small topic-compare">
          Seçtiğin konu: <strong>{labelOf(vocab?.categories ?? [], topic.category)}</strong> · Sistemin metinden
          belirlediği: <strong>{category ?? 'Belirsiz'}</strong>
          {category && info?.category === topic.category ? ' ✓' : ' (farklı)'}
        </p>
      ) : null}

      {missing.length > 0 ? (
        <div className="receipt-note">
          <strong>Ekip şu bilgileri isteyebilir:</strong> {missing.join(', ')}.
        </div>
      ) : null}
      {info?.review_required && info.review_explanations.length > 0 ? (
        <div className="receipt-note">
          <strong>Bir görevli kontrol edecek:</strong>
          <ul className="reasons">
            {info.review_explanations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="receipt-request">
        <span className="muted small">Bildirdiğin sorun</span>
        <strong>{result.title}</strong>
        <span className="description">{result.description}</span>
        <span className="muted small">Konum: {result.location}</span>
      </div>

      <div className="row wrap">
        {result.state === 'pending' ? (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={onResend}>
            Aynı talebi yeniden gönder
          </button>
        ) : null}
        {waiting ? (
          <button type="button" className="btn" disabled={busy} onClick={() => onCheck(result.ticket_id)}>
            Sonucu sorgula
          </button>
        ) : null}
        <button type="button" className={waiting ? 'btn' : 'btn btn-primary'} disabled={busy} onClick={onNew}>
          Yeni talep oluştur
        </button>
      </div>

      <details className="tech">
        <summary>Teknik ayrıntılar: karar, güven değerleri, kullanım, ücret ve süreler</summary>
        <ResultPanel run={run} vocab={vocab} wakeMs={wakeMs} />
      </details>
      <p className="muted small" style={{ margin: 0 }}>
        Bu bir demo talebidir: gerçek bir bakım ekibine iletilmez ve süre sonunda silinir.
      </p>
    </section>
  )
}

import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { Notice } from '../components/ui'
import type { DemoClient } from '../lib/demo-api'
import { DEMO_SAMPLES, validateInput } from '../lib/demo-text'
import type { DemoDecisionInput, DemoLimits, DemoState, DemoStatus } from '../lib/demo-types'
import { formatDateTime, ticketNumber } from '../lib/format'
import type { Vocabulary } from '../lib/types'
import { DEFAULT_PLACEHOLDERS, TOPICS, type Topic } from './portal-topics'
import Receipt from './Receipt'
import { useDemoDecision } from './use-demo-decision'
import { useWakeUp } from './use-wake-up'
import WakePanel, { WakeFailed } from './WakePanel'

const EMPTY: DemoDecisionInput = { title: '', description: '', location: '' }
export const ABOUT_HREF = '#/hakkinda'

/** "Taleplerim" listesinde motordan bağımsız durum adları (özet yanıtı motoru taşımaz). */
const TICKET_STATE_LABELS: Record<DemoState, string> = {
  completed: 'Değerlendirildi',
  pending: 'Kaydedildi, değerlendirme bekliyor',
  running: 'Değerlendiriliyor',
  skipped: 'Görevli tarafından değiştirildi',
  failed: 'Değerlendirilemedi; incelemeye bırakıldı',
  uncertain: 'Sonuç belirsiz',
  budget_exhausted: 'Kaydedildi; demo bütçesi doldu',
}

function Field({
  label,
  hint,
  value,
  max,
  disabled,
  multiline,
  placeholder,
  onChange,
}: {
  label: string
  hint?: string
  value: string
  max: number
  disabled: boolean
  multiline?: boolean
  placeholder: string
  onChange: (value: string) => void
}) {
  const over = value.trim().length > max
  return (
    <label className="field portal-field">
      <span>
        {label}
        {hint ? <em className="field-hint"> {hint}</em> : null}
      </span>
      {multiline ? (
        <textarea
          rows={4}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input value={value} disabled={disabled} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      )}
      <span className={`counter small ${over ? 'error-text' : 'muted'}`}>
        {value.trim().length}/{max}
      </span>
    </label>
  )
}

/** Talebi kimin karşılayacağı: her zaman açıkça yazılır (yapay zekâ mı, kural tabanlı mı). */
function engineLine(status: DemoStatus | null): string | null {
  if (!status?.accepting) return null
  if (status.is_mock) return 'Bu kurulumda talepler MOCK (sahte) sağlayıcıyla değerlendirilir; gerçek ölçüm değildir.'
  if (status.engine === 'jev')
    return 'Talebin yapay zekâ (Jev) ile ön değerlendirilir: kategori, öncelik ve eksik bilgi.'
  if (status.engine === 'rules') {
    return 'Yapay zekâ şu an kapalı; talebin kural tabanlı ön değerlendirmeyle karşılanır (ücretsiz, model çağrısı yok).'
  }
  return null
}

/**
 * Kampüs destek portalı: ziyaretçi bir arıza/şikâyet bildirir; talep kaydedilir, ön değerlendirmeyle
 * (Jev ya da Jev kapalıyken kural tabanlı motor) kategori, öncelik ve ekip belirlenir ve fiş
 * gösterilir. Sayfa açılınca yalnızca ücretsiz hazırlık isteği gider; karar isteği yalnızca
 * "Talebi gönder" ile gider.
 */
export default function DemoPage({
  client,
  vocab,
  initialTitle = '',
}: {
  client: DemoClient
  vocab: Vocabulary | null
  /** Tanıtım sayfasındaki hızlı başlangıç kutusuna yazılan başlık (isteğe bağlı). */
  initialTitle?: string
}) {
  const { state: wake, retry } = useWakeUp(client)
  const decision = useDemoDecision(client)
  const [input, setInput] = useState<DemoDecisionInput>({ ...EMPTY, title: initialTitle })
  const [topic, setTopic] = useState<Topic | null>(null)
  const [submittedTopic, setSubmittedTopic] = useState<Topic | null>(null)
  const [touched, setTouched] = useState(false)

  const ready = wake.phase === 'ready'
  const status = wake.phase === 'ready' ? wake.status : null
  const accepting = status !== null && status.accepting
  // Sunucu kesin olarak "talep alınmıyor" dediyse form kapanır; uyanırken yazmaya devam edilebilir.
  const closed = (status !== null && !status.accepting) || wake.phase === 'failed'
  const limits: DemoLimits | null = status?.limits ?? null
  const wakeMs = wake.phase === 'ready' ? wake.wakeMs : null
  const { refreshHistory } = decision
  const run = decision.run

  useEffect(() => {
    if (ready) void refreshHistory() // oturum varsa önceki talepler (tek okuma isteği)
  }, [ready, refreshHistory])

  const validation = useMemo(
    () => validateInput(input, limits ?? { title_max: 120, description_max: 1000, location_max: 120 }),
    [input, limits],
  )

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (!accepting || validation !== null || decision.busy) return
    setSubmittedTopic(topic)
    void decision.submit({
      title: input.title.trim(),
      description: input.description.trim(),
      location: input.location.trim(),
    })
  }

  function startNew() {
    decision.clear()
    setInput(EMPTY)
    setTopic(null)
    setTouched(false)
  }

  const fieldsDisabled = closed || decision.busy
  const submitDisabled = !accepting || decision.busy
  const submitReason = closed
    ? wake.phase === 'failed'
      ? 'Sunucuya ulaşılamadı.'
      : 'Talep alımı şu an kapalı.'
    : !ready
      ? 'Sunucu hazırlanıyor; bu sırada formu doldurabilirsin.'
      : null
  const engine = engineLine(status)
  const retention = status?.retention_hours ?? 72

  return (
    <div className="stack portal">
      <section className="portal-hero" aria-labelledby="portal-heading">
        <div className="portal-hero-text">
          <p className="eyebrow">Kampüs Destek · Arıza ve şikâyet bildirimi</p>
          <h1 id="portal-heading">Kampüste bir sorun mu var?</h1>
          <p className="lead">
            Arızayı ya da şikâyetini bildir; talebin numarayla kaydedilsin, önceliği belirlensin ve ilgili ekibin
            kuyruğuna yönlendirilsin.
          </p>
          <ul className="hero-points" aria-label="Talebine ne olur">
            <li>Talep numarası verilir</li>
            <li>Kategori ve öncelik belirlenir</li>
            <li>İlgili ekibe yönlendirilir</li>
          </ul>
        </div>
        <div className="hero-status">
          <WakePanel state={wake} />
        </div>
      </section>

      <p className="demo-banner" role="note">
        <strong>Demo:</strong> Bu bir portföy projesidir. Talebin gerçek bir bakım ekibine iletilmez ve {retention} saat
        sonra silinir. Acil bir durumda <strong>112</strong>&apos;yi ara. <a href={ABOUT_HREF}>Proje hakkında →</a>
      </p>

      {wake.phase === 'failed' ? <WakeFailed state={wake} onRetry={retry} /> : null}
      {status !== null && !status.accepting ? (
        <Notice tone="info">
          <strong>Talep alımı şu an kapalı.</strong> Bu sırada projenin nasıl çalıştığını ve ölçüm sonuçlarını
          inceleyebilirsin: <a href={ABOUT_HREF}>Proje hakkında</a> · <a href="#/sonuclar">Ölçüm sonuçları</a>
        </Notice>
      ) : null}
      {status?.is_mock ? (
        <Notice tone="error">
          <strong>MOCK:</strong> bu kurulum gerçek Jev&apos;e bağlı değil; sonuçlar sahte (deterministik) sağlayıcıdan
          gelir ve gerçek ölçüm değildir.
        </Notice>
      ) : null}

      {run ? (
        <Receipt
          run={run}
          vocab={vocab}
          topic={submittedTopic}
          wakeMs={wakeMs}
          busy={decision.busy}
          onCheck={(ticketId) => void decision.check(ticketId)}
          onResend={() =>
            void decision.submit({
              title: run.result.title,
              description: run.result.description,
              location: run.result.location,
            })
          }
          onNew={startNew}
        />
      ) : (
        <form className="portal-form card" onSubmit={onSubmit} aria-label="Talep formu">
          <fieldset className="topics" disabled={fieldsDisabled}>
            <legend>
              <span className="step-no" aria-hidden="true">
                1
              </span>{' '}
              Konu seç <span className="muted small">(isteğe bağlı)</span>
            </legend>
            <div className="topic-grid">
              {TOPICS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`topic${topic?.id === item.id ? ' selected' : ''}`}
                  aria-pressed={topic?.id === item.id}
                  onClick={() => setTopic(topic?.id === item.id ? null : item)}
                >
                  <span className="topic-icon">{item.icon}</span>
                  <span className="topic-label">{item.label}</span>
                  <span className="topic-hint">{item.hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="details-step" disabled={fieldsDisabled}>
            <legend>
              <span className="step-no" aria-hidden="true">
                2
              </span>{' '}
              Sorunu anlat
            </legend>
            <Field
              label="Ne oldu?"
              hint="kısa başlık"
              value={input.title}
              max={limits?.title_max ?? 120}
              disabled={fieldsDisabled}
              placeholder={topic?.titlePlaceholder ?? DEFAULT_PLACEHOLDERS.title}
              onChange={(title) => setInput({ ...input, title })}
            />
            <Field
              label="Ayrıntılar"
              hint="açıklama: ne zamandan beri, nasıl bir etki"
              value={input.description}
              max={limits?.description_max ?? 1000}
              disabled={fieldsDisabled}
              multiline
              placeholder={topic?.descriptionPlaceholder ?? DEFAULT_PLACEHOLDERS.description}
              onChange={(description) => setInput({ ...input, description })}
            />
            <Field
              label="Nerede?"
              hint="konum: blok, kat, oda"
              value={input.location}
              max={limits?.location_max ?? 120}
              disabled={fieldsDisabled}
              placeholder={DEFAULT_PLACEHOLDERS.location}
              onChange={(location) => setInput({ ...input, location })}
            />
            {touched && validation ? <p className="error-text">{validation}</p> : null}
          </fieldset>

          <div className="submit-row">
            <button
              type="submit"
              className="btn btn-primary btn-large"
              disabled={submitDisabled}
              aria-describedby={submitReason ? 'submit-reason' : undefined}
            >
              {decision.busy ? 'Gönderiliyor…' : 'Talebi gönder'}
            </button>
            {submitReason ? (
              <span id="submit-reason" className="muted small">
                {submitReason}
              </span>
            ) : null}
          </div>
          {engine ? <p className="engine-line small muted">{engine}</p> : null}

          <details className="samples" data-testid="disclosure">
            <summary>Denemek için örnek metinle doldur · verinin ne olduğu</summary>
            <div className="chips">
              {DEMO_SAMPLES.map((sample) => (
                <button
                  key={sample.id}
                  type="button"
                  className="btn btn-small"
                  disabled={fieldsDisabled}
                  onClick={() => {
                    setInput(sample.input)
                    setTouched(false)
                  }}
                >
                  {sample.label}
                </button>
              ))}
            </div>
            <p className="small muted">
              Yazdığın başlık, açıklama ve konum ön değerlendirme için işlenir; yapay zekâ açıkken{' '}
              <strong>Jev API sağlayıcısına gönderilir</strong>. Talebin ve sonucu{' '}
              <strong>{retention} saat sonra otomatik silinir</strong>; kişisel veya gizli bilgi yazma. Ücretsiz
              barındırma kullanıldığı için sunucu boştayken uyur; ilk açılış yaklaşık 1 dakika sürebilir.
            </p>
          </details>
        </form>
      )}

      {decision.error ? <Notice tone="error">{decision.error.message}</Notice> : null}

      {decision.history.length > 0 ? (
        <section className="card stack" aria-label="Taleplerim">
          <h2 className="section-title">Taleplerim</h2>
          <ul className="my-tickets">
            {decision.history.map((item) => (
              <li key={item.ticket_id}>
                <span className="ticket-no">{ticketNumber(item.ticket_number)}</span>
                <span className="my-ticket-title">{item.title}</span>
                <span className="muted small">
                  {TICKET_STATE_LABELS[item.state]} · {formatDateTime(item.created_at)}
                </span>
                <button
                  type="button"
                  className="btn btn-small"
                  disabled={decision.busy}
                  onClick={() => {
                    setSubmittedTopic(null)
                    void decision.check(item.ticket_id)
                  }}
                >
                  Göster
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

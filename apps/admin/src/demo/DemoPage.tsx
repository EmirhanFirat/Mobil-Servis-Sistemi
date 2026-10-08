import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { Notice } from '../components/ui'
import type { DemoClient } from '../lib/demo-api'
import { DEMO_SAMPLES, DEMO_STATE_LABELS, validateInput } from '../lib/demo-text'
import type { DemoDecisionInput, DemoLimits } from '../lib/demo-types'
import { formatDateTime, ticketNumber } from '../lib/format'
import type { Vocabulary } from '../lib/types'
import ResultPanel from './ResultPanel'
import { useDemoDecision } from './use-demo-decision'
import { useWakeUp } from './use-wake-up'
import WakePanel from './WakePanel'

const EMPTY: DemoDecisionInput = { title: '', description: '', location: '' }

/** Kullanıcıya, metnin nereye gideceği ve verinin ne olacağı ÖNCEDEN söylenir. */
function Disclosure({ retentionHours }: { retentionHours: number }) {
  return (
    <Notice tone="info">
      <strong>Bilmen gerekenler.</strong> Bu bir portföy demosudur. Yazdığın başlık, açıklama ve konum, değerlendirilmek
      üzere <strong>Jev API sağlayıcısına gönderilir</strong>; kişisel, gizli veya gerçek bir olay bilgisi yazma.
      Girdiğin talep ve sonucu <strong>{retentionHours} saat sonra otomatik silinir</strong>. Ücretsiz barındırma
      kullanıldığı için sunucu boştayken uyur; ilk açılış yaklaşık 1 dakika sürebilir. Bu bir acil yardım hizmeti
      değildir; can güvenliği için 112'yi ara.
    </Notice>
  )
}

function Field({
  label,
  value,
  max,
  disabled,
  multiline,
  onChange,
}: {
  label: string
  value: string
  max: number
  disabled: boolean
  multiline?: boolean
  onChange: (value: string) => void
}) {
  const over = value.trim().length > max
  return (
    <label className="field">
      <span>{label}</span>
      {multiline ? (
        <textarea rows={4} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      )}
      <span className={`small ${over ? 'error-text' : 'muted'}`}>
        {value.trim().length}/{max}
      </span>
    </label>
  )
}

export default function DemoPage({ client, vocab }: { client: DemoClient; vocab: Vocabulary | null }) {
  const { state: wake, retry } = useWakeUp(client)
  const decision = useDemoDecision(client)
  const [input, setInput] = useState<DemoDecisionInput>(EMPTY)
  const [touched, setTouched] = useState(false)

  const ready = wake.phase === 'ready'
  const status = wake.phase === 'ready' ? wake.status : null
  const enabled = status !== null && status.enabled
  const limits: DemoLimits | null = status?.limits ?? null
  const wakeMs = wake.phase === 'ready' ? wake.wakeMs : null
  const { refreshHistory } = decision

  useEffect(() => {
    if (ready) void refreshHistory() // oturum varsa önceki denemeler (tek okuma isteği)
  }, [ready, refreshHistory])

  const validation = useMemo(() => (limits ? validateInput(input, limits) : null), [input, limits])

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (!enabled || validation !== null || decision.busy) return
    void decision.submit({
      title: input.title.trim(),
      description: input.description.trim(),
      location: input.location.trim(),
    })
  }

  const disabled = !enabled || decision.busy
  const run = decision.run

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Gerçek Jev ile dene</h1>
        <p className="muted">
          Bir servis talebi yaz ya da hazır bir örnek seç. Jev; kategori, aciliyet ve eksik bilgiyi değerlendirir, karar
          talebe uygulanır ve gerçek kullanım ile ücret gösterilir. Hiçbir sonuç uydurulmaz.
        </p>
      </div>

      <WakePanel state={wake} onRetry={retry} />
      <Disclosure retentionHours={status?.retention_hours ?? 72} />
      {status?.is_mock ? (
        <Notice tone="error">
          <strong>MOCK:</strong> bu kurulum gerçek Jev'e bağlı değil; sonuçlar sahte (deterministik) sağlayıcıdan gelir
          ve gerçek ölçüm değildir.
        </Notice>
      ) : null}

      <form className="card stack" onSubmit={onSubmit} aria-label="Talep formu">
        <div>
          <span className="muted small">Hazır örnekler:</span>
          <div className="chips">
            {DEMO_SAMPLES.map((sample) => (
              <button
                key={sample.id}
                type="button"
                className="btn btn-small"
                disabled={decision.busy}
                onClick={() => {
                  setInput(sample.input)
                  setTouched(false)
                }}
              >
                {sample.label}
              </button>
            ))}
          </div>
        </div>
        <Field
          label="Başlık"
          value={input.title}
          max={limits?.title_max ?? 120}
          disabled={disabled}
          onChange={(title) => setInput({ ...input, title })}
        />
        <Field
          label="Açıklama"
          value={input.description}
          max={limits?.description_max ?? 1000}
          disabled={disabled}
          multiline
          onChange={(description) => setInput({ ...input, description })}
        />
        <Field
          label="Konum"
          value={input.location}
          max={limits?.location_max ?? 120}
          disabled={disabled}
          onChange={(location) => setInput({ ...input, location })}
        />
        {touched && validation ? <p className="error-text">{validation}</p> : null}
        <div className="row wrap">
          <button type="submit" className="btn btn-primary" disabled={disabled}>
            {decision.busy ? 'Jev değerlendiriyor…' : 'Gerçek Jev ile karar üret'}
          </button>
          {!ready ? <span className="muted small">Sunucu hazır olunca açılır.</span> : null}
          {limits ? (
            <span className="muted small">Bu oturumda en çok {limits.decisions_per_session} karar denenebilir.</span>
          ) : null}
        </div>
      </form>

      {decision.error ? <Notice tone="error">{decision.error.message}</Notice> : null}

      {run ? (
        <ResultPanel
          run={run}
          vocab={vocab}
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
        />
      ) : null}

      {decision.history.length > 0 ? (
        <section className="card stack" aria-label="Önceki denemelerim">
          <h2 style={{ margin: 0 }}>Önceki denemelerim</h2>
          <ul className="reasons">
            {decision.history.map((item) => (
              <li key={item.ticket_id}>
                {ticketNumber(item.ticket_number)} — {item.title}{' '}
                <span className="muted small">
                  ({DEMO_STATE_LABELS[item.state]}, {formatDateTime(item.created_at)})
                </span>{' '}
                <button
                  type="button"
                  className="btn btn-small"
                  disabled={decision.busy}
                  onClick={() => void decision.check(item.ticket_id)}
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

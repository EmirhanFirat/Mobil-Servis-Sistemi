import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import { Notice } from '../components/ui'
import type { ExperimentSource } from '../lib/api'
import type { DemoClient } from '../lib/demo-api'
import { DEMO_SAMPLES, DEMO_STATE_LABELS, unavailableText, validateInput } from '../lib/demo-text'
import type { DemoDecisionInput, DemoLimits } from '../lib/demo-types'
import { formatDateTime, ticketNumber } from '../lib/format'
import { loadRecordedExample } from '../lib/recorded-example'
import type { Vocabulary } from '../lib/types'
import { useResource } from '../lib/use-resource'
import RecordedExample, { RESULTS_HREF, ResultsLink } from './RecordedExample'
import ResultPanel from './ResultPanel'
import { useDemoDecision } from './use-demo-decision'
import { useWakeUp } from './use-wake-up'
import WakePanel, { WakeFailed } from './WakePanel'

const EMPTY: DemoDecisionInput = { title: '', description: '', location: '' }

/** Projeyi bilmeyen ziyaretçi için kısa tanıtım: ne olduğu, nasıl çalıştığı, neyin ölçüldüğü. */
function Intro() {
  return (
    <section className="intro card" aria-labelledby="intro-heading">
      <h1 id="intro-heading">TalepAkış</h1>
      <p className="lead">
        Kampüs ve yurt bakım ekipleri için Türkçe servis taleplerini kategorize eden, önceliklendiren ve ilgili ekibin
        kuyruğuna yönlendiren sistem; bir mobil uygulama (React Native) ve bir yönetici paneli içerir.
      </p>
      <ol className="steps" aria-label="Nasıl çalışır">
        <li>
          <span className="step-no" aria-hidden="true">
            1
          </span>
          <span>
            <strong>Talep yaz</strong>
            <span className="muted small">Başlık, açıklama ve konum</span>
          </span>
        </li>
        <li>
          <span className="step-no" aria-hidden="true">
            2
          </span>
          <span>
            <strong>Model değerlendirir</strong>
            <span className="muted small">Kategori, öncelik ve eksik bilgiyi belirler</span>
          </span>
        </li>
        <li>
          <span className="step-no" aria-hidden="true">
            3
          </span>
          <span>
            <strong>Ekibe düşer</strong>
            <span className="muted small">Talep ilgili ekibin kuyruğuna yönlendirilir</span>
          </span>
        </li>
      </ol>
      <p className="small" style={{ margin: 0 }}>
        Araştırma: Jev, ekonomik bir LLM ve ikisini birleştiren hibrit yaklaşım aynı taleplerde doğruluk, süre ve ücret
        açısından karşılaştırılıyor. <a href={RESULTS_HREF}>Ölçüm sonuçları →</a>
      </p>
    </section>
  )
}

/** Metnin nereye gideceği ve verinin ne olacağı ÖNCEDEN söylenir: kısa not + katlanan tam metin. */
function Disclosure({ retentionHours }: { retentionHours: number }) {
  return (
    <div className="form-note small muted" data-testid="disclosure">
      <p>
        Yazdığın metin <strong>Jev API sağlayıcısına gönderilir</strong> ve{' '}
        <strong>{retentionHours} saat sonra otomatik silinir</strong>; kişisel veya gizli bilgi yazma. Bu bir acil
        yardım hizmeti değildir; can güvenliği için 112&apos;yi ara.
      </p>
      <details>
        <summary>Bilmen gerekenler</summary>
        <p>
          Bu bir portföy demosudur. Yazdığın başlık, açıklama ve konum, değerlendirilmek üzere Jev API sağlayıcısına
          gönderilir; kişisel, gizli veya gerçek bir olay bilgisi yazma. Girdiğin talep ve sonucu {retentionHours} saat
          sonra otomatik silinir. Ücretsiz barındırma kullanıldığı için sunucu boştayken uyur; ilk açılış yaklaşık 1
          dakika sürebilir. Bu bir acil yardım hizmeti değildir; can güvenliği için 112&apos;yi ara.
        </p>
      </details>
    </div>
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

/** Kayıtlı örnekler statik dosyadan, bellekteki kaynaktan okunur (ağ veya model çağrısı yok). */
function useRecorded(experiments: ExperimentSource | null) {
  const load = useCallback(
    async () => ({ value: experiments ? await loadRecordedExample(experiments) : null }),
    [experiments],
  )
  const { data, loading } = useResource(load)
  return { recorded: data?.value ?? null, loading: loading && experiments !== null }
}

export default function DemoPage({
  client,
  vocab,
  experiments = null,
}: {
  client: DemoClient
  vocab: Vocabulary | null
  /** Kayıtlı deney sonuçları (statik); canlı deneme kapalıyken örnek karar göstermek için. */
  experiments?: ExperimentSource | null
}) {
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
  const reason = status ? unavailableText(status) : null
  // Canlı deneme yapılamıyorsa (kapalı/bütçe doldu ya da sunucuya ulaşılamadı) kayıtlı örnek gösterilir.
  const offline = reason !== null || wake.phase === 'failed'
  const { recorded, loading: recordedLoading } = useRecorded(experiments)

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
  const disabledReason = !ready
    ? wake.phase === 'failed'
      ? 'Sunucuya ulaşılamadı.'
      : 'Sunucu hazır olunca açılır.'
    : !enabled
      ? 'Canlı deneme şu an kapalı'
      : null

  return (
    <div className="stack">
      <Intro />

      <section className="stack" aria-labelledby="try-heading">
        <div className="section-head">
          <h2 id="try-heading">Gerçek Jev ile dene</h2>
          <WakePanel state={wake} />
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Bir servis talebi yaz ya da hazır bir örnek seç. Jev&apos;in kararı talebe uygulanır; gerçek kullanım ve ücret
          gösterilir. Hiçbir sonuç uydurulmaz.
        </p>

        {wake.phase === 'failed' ? <WakeFailed state={wake} onRetry={retry} /> : null}
        {reason ? (
          <Notice tone="info">
            <strong>{reason}</strong>{' '}
            {recorded
              ? 'Aşağıda kayıtlı bir örnek kararı ve ölçüm sonuçlarını inceleyebilirsin.'
              : 'Kayıtlı ölçüm sonuçlarını inceleyebilirsin.'}
          </Notice>
        ) : null}
        {status?.is_mock ? (
          <Notice tone="error">
            <strong>MOCK:</strong> bu kurulum gerçek Jev&apos;e bağlı değil; sonuçlar sahte (deterministik) sağlayıcıdan
            gelir ve gerçek ölçüm değildir.
          </Notice>
        ) : null}

        {offline ? (
          recorded ? (
            <RecordedExample example={recorded} vocab={vocab} />
          ) : recordedLoading ? null : (
            <div className="row wrap">
              <ResultsLink />
            </div>
          )
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
                  disabled={disabled}
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
            <button
              type="submit"
              className="btn btn-primary"
              disabled={disabled}
              aria-describedby={disabledReason ? 'submit-reason' : undefined}
            >
              {decision.busy ? 'Jev değerlendiriyor…' : 'Gerçek Jev ile karar üret'}
            </button>
            {disabledReason ? (
              <span id="submit-reason" className="muted small">
                {disabledReason}
              </span>
            ) : null}
            {limits && enabled ? (
              <span className="muted small">Bu oturumda en çok {limits.decisions_per_session} karar denenebilir.</span>
            ) : null}
          </div>
          <Disclosure retentionHours={status?.retention_hours ?? 72} />
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
            <h3 style={{ margin: 0 }}>Önceki denemelerim</h3>
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
      </section>
    </div>
  )
}

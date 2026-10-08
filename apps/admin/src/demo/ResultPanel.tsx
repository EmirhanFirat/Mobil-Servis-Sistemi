import { Badge, Notice } from '../components/ui'
import { DEMO_STATE_LABELS, answerText, confidenceText, durationText, questionLabel, tokenText } from '../lib/demo-text'
import type { DemoDecisionResult, DemoState } from '../lib/demo-types'
import { NA, formatUsd } from '../lib/experiments'
import { labelOf, ticketNumber } from '../lib/format'
import type { Vocabulary } from '../lib/types'
import type { DecisionRun } from './use-demo-decision'

const TONE: Record<DemoState, 'info' | 'error' | 'success'> = {
  completed: 'success',
  pending: 'info',
  running: 'info',
  skipped: 'info',
  failed: 'error',
  uncertain: 'error',
  budget_exhausted: 'error',
}

function Facts({ result, vocab }: { result: DemoDecisionResult; vocab: Vocabulary | null }) {
  const info = result.decision
  if (!info) return null
  const category = info.category === null ? 'Belirsiz' : labelOf(vocab?.categories ?? [], info.category)
  const priority = info.priority === null ? 'Belirsiz' : labelOf(vocab?.priorities ?? [], info.priority)
  const status = labelOf(vocab?.statuses ?? [], result.ticket_status)
  const missing = info.missing_info.map((code) => labelOf(vocab?.missing_info ?? [], code))
  return (
    <dl className="facts">
      <dt>Kaynak</dt>
      <dd>
        {info.is_mock ? (
          <Badge kind="source-mock">MOCK — gerçek model değil</Badge>
        ) : (
          <Badge kind="source-real">Gerçek Jev ({info.model})</Badge>
        )}
      </dd>
      <dt>Kategori</dt>
      <dd>{category}</dd>
      <dt>Öncelik</dt>
      <dd>{priority}</dd>
      <dt>Karar talebe</dt>
      <dd>
        {info.applied
          ? `uygulandı (talep durumu: ${status})`
          : `uygulanmadı (${info.applied_outcome === 'skipped_human_edit' ? 'insan değişikliği korundu' : 'talep artık yeni değil'})`}
      </dd>
      <dt>Eksik bilgi</dt>
      <dd>{missing.length > 0 ? missing.join(', ') : 'yok'}</dd>
      <dt>İnsan incelemesi</dt>
      <dd>
        {info.review_required ? 'gerekiyor' : 'gerekmiyor'}
        {info.review_explanations.length > 0 ? (
          <ul className="reasons">
            {info.review_explanations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        ) : null}
      </dd>
    </dl>
  )
}

function Judgments({ result, vocab }: { result: DemoDecisionResult; vocab: Vocabulary | null }) {
  const info = result.decision
  if (!info || info.judgments.length === 0) return null
  const labels = {
    categories: (code: string) => (code === 'unclear' ? 'Belirsiz' : labelOf(vocab?.categories ?? [], code)),
    priorities: (code: string) => (code === 'unclear' ? 'Belirsiz' : labelOf(vocab?.priorities ?? [], code)),
  }
  return (
    <details>
      <summary>Soru bazında yargılar ve güven değerleri ({info.judgments.length})</summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Soru</th>
              <th>Cevap</th>
              <th>Güven</th>
            </tr>
          </thead>
          <tbody>
            {info.judgments.map((judgment) => (
              <tr key={judgment.question}>
                <td>{questionLabel(judgment.question)}</td>
                <td>{answerText(judgment, labels)}</td>
                <td>{confidenceText(judgment)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        “Jev güveni” Jev'in kendisinin verdiği değerdir; “türetilmiş marj”, evet/hayır olasılığından bizim
        hesapladığımız farklı bir sayıdır. İkisi eşdeğer değildir.
      </p>
    </details>
  )
}

function Usage({ result }: { result: DemoDecisionResult }) {
  const usage = result.usage
  if (!usage) return <p className="muted small">Jev'e bu talep için istek gönderilmedi; kullanım ve ücret yok.</p>
  return (
    <dl className="facts">
      <dt>Jev çağrısı</dt>
      <dd>{usage.calls}</dd>
      <dt>Girdi tokenı</dt>
      <dd>{tokenText(usage.input_tokens)}</dd>
      <dt>Çıktı tokenı</dt>
      <dd>
        {tokenText(usage.output_tokens)}
        {usage.output_tokens_free && usage.output_tokens !== null ? ' (çıktı tokenları ücretsiz)' : ''}
      </dd>
      <dt>Ücret</dt>
      <dd>
        {usage.cost_basis === 'provider_usage' ? (
          <>
            {formatUsd(usage.cost_usd)} <span className="muted small">(Jev'in bildirdiği kullanımdan hesaplandı)</span>
          </>
        ) : (
          <>
            bilinmiyor <span className="muted small">(kullanım bildirilmedi; bütçede en kötü bedelle sayılır)</span>
          </>
        )}
      </dd>
      <dt>Fiyat</dt>
      <dd className="small muted">{usage.price_note}</dd>
    </dl>
  )
}

function Timings({ run, wakeMs }: { run: DecisionRun; wakeMs: number | null }) {
  const { timings } = run.result
  return (
    <div className="timing-grid" data-testid="timings">
      <div className="card">
        <span className="muted small">Sunucu uyanma</span>
        <strong>{wakeMs === null ? NA : durationText(wakeMs)}</strong>
        <span className="muted small">Yalnızca ilk ziyaret; model süresi değil</span>
      </div>
      <div className="card">
        <span className="muted small">Uçtan uca bekleme</span>
        <strong>{durationText(run.e2eMs)}</strong>
        <span className="muted small">Bu istek: düğme → yanıt (istemci ölçümü)</span>
      </div>
      <div className="card">
        <span className="muted small">Jev çağrısı</span>
        <strong>{durationText(timings.jev_call_ms)}</strong>
        <span className="muted small">Sunucudan Jev'e giden istek (ağ dahil)</span>
      </div>
    </div>
  )
}

export default function ResultPanel({
  run,
  vocab,
  wakeMs,
  busy,
  onCheck,
  onResend,
}: {
  run: DecisionRun
  vocab: Vocabulary | null
  wakeMs: number | null
  busy: boolean
  onCheck: (ticketId: string) => void
  onResend: () => void
}) {
  const { result } = run
  const waiting = result.state === 'pending' || result.state === 'running'
  return (
    <section className="card stack" aria-label="Sonuç">
      <div className="row wrap">
        <h2 style={{ margin: 0 }}>Sonuç — {ticketNumber(result.ticket_number)}</h2>
        <Badge kind={result.state === 'completed' ? 'source-real' : undefined}>{DEMO_STATE_LABELS[result.state]}</Badge>
      </div>
      <Notice tone={TONE[result.state]}>{result.message}</Notice>
      {waiting ? (
        <div className="row wrap">
          {result.state === 'pending' ? (
            <button type="button" className="btn btn-primary" disabled={busy} onClick={onResend}>
              Aynı talebi yeniden gönder
            </button>
          ) : null}
          <button type="button" className="btn" disabled={busy} onClick={() => onCheck(result.ticket_id)}>
            Sonucu sorgula
          </button>
          <span className="muted small">
            Aynı metin ikinci bir Jev çağrısı açmaz; sorgulamak hiçbir çağrı başlatmaz.
          </span>
        </div>
      ) : null}

      <div>
        <h3>Gönderdiğin talep</h3>
        <p style={{ margin: 0 }}>
          <strong>{result.title}</strong>
        </p>
        <p className="description">{result.description}</p>
        <p className="muted small">Konum: {result.location}</p>
      </div>

      <Facts result={result} vocab={vocab} />
      <Judgments result={result} vocab={vocab} />
      <h3>Kullanım ve ücret (gerçek, bildirilen)</h3>
      <Usage result={result} />
      <h3>Süreler (birbirinden ayrı ölçülür)</h3>
      <Timings run={run} wakeMs={wakeMs} />
      <p className="muted small">
        Bu, TEK bir isteğin ölçümüdür; benchmark sonucu değildir. Etiketi olmayan ziyaretçi taleplerinden doğruluk oranı
        çıkarılmaz. Geçmiş benchmark sonuçları “Ölçüm sonuçları” sayfasındadır ve bu ölçümlerle karıştırılmaz. Kalan
        hakkın: {result.decisions_remaining}.
      </p>
    </section>
  )
}

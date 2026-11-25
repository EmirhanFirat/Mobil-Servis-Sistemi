import { Badge } from '../components/ui'
import { answerText, confidenceText, durationText, questionLabel, tokenText } from '../lib/demo-text'
import type { DemoDecisionResult, DemoJudgment, DemoUsage } from '../lib/demo-types'
import { NA, formatUsd } from '../lib/experiments'
import { labelOf } from '../lib/format'
import type { Vocabulary } from '../lib/types'
import type { DecisionRun } from './use-demo-decision'

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
        {result.engine === 'rules' || info.provider === 'rule_based' ? (
          <Badge kind="source-rule">Kural tabanlı ({info.model ?? 'kurallar'}) — yapay zekâ değil</Badge>
        ) : info.is_mock ? (
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

/** Soru bazında yargılar: canlı sonuçta ve kayıtlı örnekte aynı tablo. */
export function JudgmentsDetails({ judgments, vocab }: { judgments: DemoJudgment[]; vocab: Vocabulary | null }) {
  if (judgments.length === 0) return null
  const labels = {
    categories: (code: string) => (code === 'unclear' ? 'Belirsiz' : labelOf(vocab?.categories ?? [], code)),
    priorities: (code: string) => (code === 'unclear' ? 'Belirsiz' : labelOf(vocab?.priorities ?? [], code)),
  }
  return (
    <details>
      <summary>Soru bazında yargılar ve güven değerleri ({judgments.length})</summary>
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
            {judgments.map((judgment) => (
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

/** Kullanım ve ücret: bilinmeyen değer "bilinmiyor"/"bildirilmedi" yazılır, sıfır gösterilmez. */
export function UsageFacts({
  usage,
  unknownNote = 'kullanım bildirilmedi; bütçede en kötü bedelle sayılır',
}: {
  usage: DemoUsage | null
  /** Ücret bilinmediğinde parantez içindeki açıklama (canlı sonuç ile kayıtlı örnekte farklıdır). */
  unknownNote?: string
}) {
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
            bilinmiyor <span className="muted small">({unknownNote})</span>
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
      {run.result.engine === 'rules' ? (
        <div className="card">
          <span className="muted small">Kural değerlendirmesi</span>
          <strong>{durationText(timings.job_ms)}</strong>
          <span className="muted small">Sunucudaki karar işi; model çağrısı yok</span>
        </div>
      ) : (
        <div className="card">
          <span className="muted small">Jev çağrısı</span>
          <strong>{durationText(timings.jev_call_ms)}</strong>
          <span className="muted small">Sunucudan Jev'e giden istek (ağ dahil)</span>
        </div>
      )}
    </div>
  )
}

/**
 * Fişin içindeki "Teknik ayrıntılar": karar, yargılar, kullanım/ücret ve süreler. Talep numarası,
 * ileti, düğmeler ve talep metni fişte zaten gösterilir.
 */
export default function ResultPanel({
  run,
  vocab,
  wakeMs,
}: {
  run: DecisionRun
  vocab: Vocabulary | null
  wakeMs: number | null
}) {
  const { result } = run
  return (
    <div className="stack" data-testid="technical-details">
      <Facts result={result} vocab={vocab} />
      <JudgmentsDetails judgments={result.decision?.judgments ?? []} vocab={vocab} />
      <h3>Kullanım ve ücret (gerçek, bildirilen)</h3>
      <UsageFacts usage={result.usage} />
      <h3>Süreler (birbirinden ayrı ölçülür)</h3>
      <Timings run={run} wakeMs={wakeMs} />
      <p className="muted small" style={{ margin: 0 }}>
        Bu, TEK bir isteğin ölçümüdür; benchmark sonucu değildir. Etiketi olmayan ziyaretçi taleplerinden doğruluk oranı
        çıkarılmaz. Kalan hakkın: {result.decisions_remaining}.
      </p>
    </div>
  )
}

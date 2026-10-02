import {
  answerText,
  applyOutcomeText,
  confidenceText,
  costText,
  decisionSource,
  jobLine,
  questionText,
  reasonText,
  unresolvedQuestions,
} from '../lib/decision'
import { formatDateTime, labelOf } from '../lib/format'
import type { DecisionPanelData, Vocabulary } from '../lib/types'
import { Badge, Notice } from './ui'

interface Props {
  /** Yalnızca yöneticiye döner; yoksa kart hiç gösterilmez. */
  panel: DecisionPanelData | null | undefined
  vocab: Vocabulary
}

/**
 * Karar motoru önerisi: kaynağı (kural/mock/gerçek), ürettiği ilk tahmin ve talebe uygulanıp
 * uygulanmadığı. Bu, talebin güncel alanlarından AYRI bir kayıttır; yönetici düzeltmesi bunu
 * değiştirmez.
 */
export function DecisionCard({ panel, vocab }: Props) {
  if (!panel) return null
  const { job, decision } = panel

  return (
    <section className="panel" aria-labelledby="panel-decision">
      <h3 id="panel-decision">Karar motoru önerisi</h3>

      {!job && !decision ? (
        <p className="muted">Bu talep için karar işi oluşturulmadı.</p>
      ) : null}

      {job ? (
        <Notice tone={jobLine(job).tone}>{jobLine(job).text}</Notice>
      ) : null}

      {decision ? <DecisionBody decision={decision} vocab={vocab} /> : null}
    </section>
  )
}

function DecisionBody({
  decision,
  vocab,
}: {
  decision: NonNullable<DecisionPanelData['decision']>
  vocab: Vocabulary
}) {
  const source = decisionSource(decision)
  const missing = decision.missing_info.map((code) => labelOf(vocab.missing_info, code))
  const unresolved = unresolvedQuestions(decision.judgments)

  return (
    <>
      <p className="row wrap">
        <Badge kind={`source-${source.kind}`}>{source.title}</Badge>
        <span className="muted">{source.detail}</span>
      </p>
      {source.kind === 'mock' ? (
        <Notice tone="info">
          Bu karar sahte (mock) sağlayıcıyla üretildi; gerçek model ölçümü değildir.
        </Notice>
      ) : null}

      <dl className="facts">
        <dt>Önerilen kategori</dt>
        <dd>{decision.category ? labelOf(vocab.categories, decision.category) : 'Belirsiz'}</dd>
        <dt>Önerilen öncelik</dt>
        <dd>{decision.priority ? labelOf(vocab.priorities, decision.priority) : 'Belirsiz'}</dd>
        <dt>Eksik bilgi</dt>
        <dd>{missing.length > 0 ? missing.join(', ') : '—'}</dd>
        {unresolved.length > 0 ? (
          <>
            <dt>Kesin yanıt yok</dt>
            <dd>
              {unresolved.map(questionText).join(' · ')}
              <p className="muted">
                Bu sorular için karara alınmış kesin bir cevap yok (belirsiz, çekimser veya sorulmadı).
                “Eksik bilgi” satırında görünmemeleri “eksik değil” anlamına gelmez.
              </p>
            </dd>
          </>
        ) : null}
        <dt>İnceleme</dt>
        <dd>
          {decision.review_required ? (
            <>
              Gerekiyor
              <ul className="reasons">
                {decision.review_reasons.map((code) => (
                  <li key={code}>{reasonText(code)}</li>
                ))}
              </ul>
            </>
          ) : (
            'Gerekmiyor'
          )}
        </dd>
        <dt>Talebe etkisi</dt>
        <dd>
          {applyOutcomeText(decision.applied_outcome)}
          {decision.applied_at ? ` (${formatDateTime(decision.applied_at)})` : ''}
        </dd>
        <dt>Çağrılar ve ücret</dt>
        <dd>{costText(decision)}</dd>
        <dt>Karar zamanı</dt>
        <dd>{formatDateTime(decision.created_at)}</dd>
      </dl>

      {decision.judgments.length > 0 ? (
        <details>
          <summary>Soru bazında yargılar ({decision.judgments.length})</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Soru</th>
                  <th>Cevap</th>
                  <th>Güven</th>
                  <th>Kaynak</th>
                </tr>
              </thead>
              <tbody>
                {decision.judgments.map((judgment, index) => (
                  <tr key={`${judgment.question}-${judgment.source}-${index}`}>
                    <td>{questionText(judgment.question)}</td>
                    <td>{answerText(judgment, vocab)}</td>
                    <td>{confidenceText(judgment)}</td>
                    <td>
                      {judgment.source ?? '—'}
                      {judgment.adopted ? '' : ' (karara alınmadı)'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </>
  )
}

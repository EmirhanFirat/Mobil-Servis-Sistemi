import { useState } from 'react'

import { Badge } from '../components/ui'
import { reasonText } from '../lib/decision'
import { durationText } from '../lib/demo-text'
import { runDate, scopeLabel } from '../lib/experiments'
import { labelOf } from '../lib/format'
import type { RecordedExample as Recorded } from '../lib/recorded-example'
import type { Vocabulary } from '../lib/types'
import { JudgmentsDetails, UsageFacts } from './ResultPanel'

export const RESULTS_HREF = '#/sonuclar'

/** Kayıtlı karar yoksa ziyaretçiyi ölçüm sonuçlarına yönlendiren belirgin düğme. */
export function ResultsLink({ label = 'Ölçüm sonuçlarını incele' }: { label?: string }) {
  return (
    <a className="btn btn-primary" href={RESULTS_HREF}>
      {label} →
    </a>
  )
}

/**
 * Canlı deneme kapalıyken gösterilir. İçerik, kayıtlı GERÇEK bir deneyden okunur ve "Kayıtlı örnek"
 * etiketiyle canlı sonuçtan açıkça ayrılır; model çağrısı yapılmaz, hiçbir değer uydurulmaz.
 */
export default function RecordedExample({ example, vocab }: { example: Recorded; vocab: Vocabulary | null }) {
  const [index, setIndex] = useState(0)
  const { run, samples } = example
  const { sample, jev, usage } = samples[index % samples.length]
  const date = runDate(run)
  const category =
    jev.category === null || jev.category === 'unclear' ? 'Belirsiz' : labelOf(vocab?.categories ?? [], jev.category)
  const priority = jev.priority === null ? 'Belirsiz' : labelOf(vocab?.priorities ?? [], jev.priority)
  const missing = jev.missing_info.map((code) => labelOf(vocab?.missing_info ?? [], code))

  return (
    <section className="card stack recorded" aria-label="Kayıtlı örnek">
      <div className="row wrap">
        <Badge kind="recorded">Kayıtlı örnek · {date}</Badge>
        <span className="muted small">{scopeLabel(run)}</span>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Bu bir canlı istek değil: {date} tarihli kayıtlı deneyde Jev&apos;in aşağıdaki örnek talep için verdiği
        karardır. Kart açılırken hiçbir model çağrısı yapılmaz.
      </p>

      <div>
        <h3>Örnek talep</h3>
        <p style={{ margin: 0 }}>
          <strong>{sample.title}</strong>
        </p>
        <p className="description">{sample.description}</p>
        <p className="muted small">Konum: {sample.location}</p>
      </div>

      <dl className="facts">
        <dt>Kaynak</dt>
        <dd>
          <Badge kind="source-real">Gerçek Jev ({jev.info.model ?? 'model bilinmiyor'})</Badge>
        </dd>
        <dt>Kategori</dt>
        <dd>{category}</dd>
        <dt>Öncelik</dt>
        <dd>{priority}</dd>
        <dt>Eksik bilgi</dt>
        <dd>{missing.length > 0 ? missing.join(', ') : 'yok'}</dd>
        <dt>İnsan incelemesi</dt>
        <dd>
          {jev.review_required === null ? 'bilinmiyor' : jev.review_required ? 'gerekiyor' : 'gerekmiyor'}
          {jev.review_reasons.length > 0 ? (
            <ul className="reasons">
              {jev.review_reasons.map((code) => (
                <li key={code}>{reasonText(code)}</li>
              ))}
            </ul>
          ) : null}
        </dd>
        <dt>Karar süresi</dt>
        <dd>
          {durationText(jev.latency_ms)} <span className="muted small">(kayıt anında ölçülen uçtan uca süre)</span>
        </dd>
      </dl>
      <JudgmentsDetails judgments={jev.judgments} vocab={vocab} />
      <h3>Kullanım ve ücret (kayıtlı)</h3>
      <UsageFacts usage={usage} unknownNote="kayıtta ücret bilinmiyor; sıfır sayılmaz" />

      <div className="row wrap">
        {samples.length > 1 ? (
          <button type="button" className="btn" onClick={() => setIndex((value) => (value + 1) % samples.length)}>
            Başka kayıtlı örnek ({(index % samples.length) + 1}/{samples.length})
          </button>
        ) : null}
        <ResultsLink label="Tüm ölçüm sonuçları" />
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Tek bir örneğin kaydıdır; doğruluk veya genel performans iddiası değildir.
      </p>
    </section>
  )
}

import { useCallback } from 'react'

import type { ExperimentSource } from '../lib/api'
import { loadRecordedExample } from '../lib/recorded-example'
import type { Vocabulary } from '../lib/types'
import { useResource } from '../lib/use-resource'
import RecordedExample, { RESULTS_HREF, ResultsLink } from './RecordedExample'

/** Kayıtlı örnekler statik dosyadan, bellekteki kaynaktan okunur (ağ veya model çağrısı yok). */
function useRecorded(experiments: ExperimentSource | null) {
  const load = useCallback(
    async () => ({
      value: experiments ? await loadRecordedExample(experiments) : null,
    }),
    [experiments],
  )
  const { data, loading } = useResource(load)
  return {
    recorded: data?.value ?? null,
    loading: loading && experiments !== null,
  }
}

const STEPS = [
  {
    title: 'Talep yazılır',
    text: 'Başlık, açıklama ve konum; mobil uygulamadan veya bu portaldan',
  },
  {
    title: 'Ön değerlendirme',
    text: 'Kategori, öncelik ve eksik bilgi belirlenir (Jev ya da kurallar)',
  },
  {
    title: 'Ekibe düşer',
    text: 'Atama deterministik kurallarla yapılır; belirsiz talep insana gider',
  },
]

/**
 * Proje hakkında: ne olduğu, nasıl çalıştığı, araştırma sorusu ve kayıtlı (gerçek ölçümden) bir
 * örnek karar. Portalın ana sayfası şikâyet formudur; teknik anlatım burada durur.
 */
export default function AboutPage({
  vocab,
  experiments,
}: {
  vocab: Vocabulary | null
  experiments: ExperimentSource | null
}) {
  const { recorded, loading } = useRecorded(experiments)
  return (
    <div className="stack">
      <section className="intro card" aria-labelledby="intro-heading">
        <h1 id="intro-heading">TalepAkış hakkında</h1>
        <p className="lead">
          Kampüs ve yurt bakım ekipleri için Türkçe servis taleplerini kategorize eden, önceliklendiren ve ilgili ekibin
          kuyruğuna yönlendiren sistem; bir mobil uygulama (React Native), bir yönetici paneli ve bu demo portalından
          oluşur.
        </p>
        <ol className="steps" aria-label="Nasıl çalışır">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <span className="step-no" aria-hidden="true">
                {index + 1}
              </span>
              <span>
                <strong>{step.title}</strong>
                <span className="muted small">{step.text}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className="small" style={{ margin: 0 }}>
          Araştırma sorusu: Türkçe servis taleplerinde Jev, ekonomik bir LLM ve ikisini birleştiren hibrit yaklaşım
          doğruluk, süre ve ücret açısından nasıl karşılaştırılır? <a href={RESULTS_HREF}>Ölçüm sonuçları →</a>
        </p>
      </section>

      <section className="card stack" aria-labelledby="engines-heading">
        <h2 id="engines-heading" className="section-title">
          Portaldaki talepleri kim değerlendiriyor?
        </h2>
        <p className="small" style={{ margin: 0 }}>
          Yapay zekâ (Jev) açıkken talep Jev&apos;e gönderilir ve fişte <strong>Yapay zekâ ön değerlendirmesi</strong>{' '}
          yazar. Jev kapalıyken talep yine kaydedilir ve ücretsiz <strong>kural tabanlı</strong> motorla
          değerlendirilir; fiş bunu açıkça söyler. Hangi durumda olursa olsun ekip ataması deterministik kurallarla
          yapılır ve model çıktısı hiçbir yetki vermez.
        </p>
      </section>

      {recorded ? (
        <RecordedExample example={recorded} vocab={vocab} />
      ) : loading ? null : (
        <div className="row">
          <ResultsLink />
        </div>
      )}
    </div>
  )
}

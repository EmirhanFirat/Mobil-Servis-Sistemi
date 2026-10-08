import { ErrorBox, Loading } from '../components/ui'
import type { StaticBundle } from '../lib/static-experiments'
import { ExperimentsPage } from '../pages/ModelComparisonPage'

/**
 * Önceden kaydedilmiş benchmark sonuçları: statik dosyadan okunur, API uyanmadan açılır ve canlı
 * demoda ziyaretçilerin tek tek ölçümleriyle KARIŞTIRILMAZ.
 */
export default function ResultsPage({
  bundle,
  error,
  loading,
  onRetry,
}: {
  bundle: StaticBundle | null
  error: Error | null
  loading: boolean
  onRetry: () => void
}) {
  if (loading && !bundle) return <Loading message="Kayıtlı sonuçlar yükleniyor…" />
  if (error && !bundle) return <ErrorBox error={error} onRetry={onRetry} />
  if (!bundle) return null
  return (
    <ExperimentsPage
      api={bundle.source}
      vocab={bundle.vocabulary}
      title="Ölçüm sonuçları"
      description={
        <>
          Daha önce kaydedilmiş gerçek deneylerin (Jev, LLM ve hibrit) sonuçları. Bu sayfa statik bir dosyadan okunur:
          sunucu uyanmadan açılır, hiçbir model çağrısı yapmaz. Canlı demoda denediğin tek tek istekler buradaki
          benchmark ölçümleriyle karıştırılmaz.
        </>
      }
      empty="Henüz yayımlanmış bir deney sonucu yok. Bu ekran örnek veya uydurma rakam göstermez."
    />
  )
}

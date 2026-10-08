import { useCallback, useRef, useState, type ReactNode, type RefObject } from 'react'
import { useSearchParams } from 'react-router'

import { BarChart, ChartSvg, PairedBarChart } from '../components/experiment-charts'
import {
  ComparisonTable,
  Conditions,
  ExportBar,
  Reconciliation,
  RunPicker,
  SampleInspector,
  SampleTable,
  Warnings,
} from '../components/experiment-views'
import ShareCard from '../components/ShareCard'
import { Empty, ErrorBox, Loading, Notice } from '../components/ui'
import type { ExperimentSource } from '../lib/api'
import { costBarItems, latencyPairItems } from '../lib/chart-data'
import { useSession } from '../lib/auth-context'
import type { ExperimentDetail, ExperimentRun, ExperimentSample } from '../lib/experiment-types'
import {
  SAMPLE_FILTERS,
  buildCsv,
  buildMarkdown,
  defaultExampleId,
  exportFileName,
  filterSamples,
  type SampleFilter,
} from '../lib/experiments'
import { downloadBlob, downloadText, svgToPngBlob } from '../lib/image-export'
import type { Vocabulary } from '../lib/types'
import { useResource } from '../lib/use-resource'

type Tab = 'karsilastirma' | 'ornekler' | 'paylasim'

const TABS: { key: Tab; label: string }[] = [
  { key: 'karsilastirma', label: 'Karşılaştırma' },
  { key: 'ornekler', label: 'Örnek bazında inceleme' },
  { key: 'paylasim', label: 'Paylaşım görünümü' },
]

/** Yönetici paneli: kayıtlı deneyler API'den okunur (yalnızca yönetici). */
export default function ModelComparisonPage() {
  const { api, vocab } = useSession()
  return <ExperimentsPage api={api} vocab={vocab} />
}

/**
 * Karşılaştırma ekranının kendisi. Veri kaynağı enjekte edilir: yönetici panelinde API, herkese açık
 * demoda önceden hazırlanmış statik dosya (API uyanmadan açılır). İkisi de yalnızca OKUR.
 */
export function ExperimentsPage({
  api,
  vocab,
  title = 'Model karşılaştırma',
  description = 'Jev, LLM ve hibrit stratejilerin kayıtlı deneylerdeki ölçümleri. Bu sayfa yalnızca kayıtlı dosyaları okur; açmak, yenilemek, süzmek veya dışa aktarmak hiçbir model çağrısı başlatmaz.',
  empty,
}: {
  api: ExperimentSource
  vocab: Vocabulary
  title?: string
  description?: ReactNode
  /** Deney yoksa gösterilecek metin (varsayılan, geliştirme ortamına özgü yönergedir). */
  empty?: string
}) {
  const [params, setParams] = useSearchParams()
  const loadList = useCallback(() => api.listExperiments(), [api])
  const { data, error, loading, retry } = useResource(loadList)

  function update(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value === null) merged.delete(key)
      else merged.set(key, value)
    }
    setParams(merged)
  }

  return (
    <>
      <div className="page-head">
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>

      {loading && !data ? (
        <Loading message="Kayıtlı deneyler aranıyor…" />
      ) : error && !data ? (
        <ErrorBox error={error} onRetry={retry} />
      ) : data && data.runs.length === 0 ? (
        <Empty
          title="Kayıtlı deney bulunamadı"
          message={
            empty ??
            (data.runs_dir_found
              ? "evaluation/runs klasörü boş. Deney kayıtları Git'e girmez; yerelde `python -m app.evaluation run ...` ile üretilir. Bu ekran örnek veya uydurma rakam göstermez."
              : "evaluation/runs klasörü bulunamadı. Deney kayıtları Git'e girmez; yerelde `python -m app.evaluation run ...` ile üretilir. Bu ekran örnek veya uydurma rakam göstermez.")
          }
        />
      ) : data ? (
        <Experiments api={api} vocab={vocab} runs={data.runs} params={params} onUpdate={update} />
      ) : null}
    </>
  )
}

function defaultRun(runs: ExperimentRun[]): ExperimentRun {
  return runs.find((run) => run.status === 'complete') ?? runs[0]
}

function Experiments({
  api,
  vocab,
  runs,
  params,
  onUpdate,
}: {
  api: ExperimentSource
  vocab: Vocabulary
  runs: ExperimentRun[]
  params: URLSearchParams
  onUpdate: (next: Record<string, string | null>) => void
}) {
  const selected = runs.find((run) => run.id === params.get('deney')) ?? defaultRun(runs)
  return (
    <div className="stack">
      <RunPicker
        list={{ runs_dir_found: true, runs }}
        selected={selected.id}
        onSelect={(id) => onUpdate({ deney: id, ornek: null, gorunum: null })}
      />
      <RunView key={selected.id} api={api} vocab={vocab} run={selected} params={params} onUpdate={onUpdate} />
    </div>
  )
}

function RunView({
  api,
  vocab,
  run,
  params,
  onUpdate,
}: {
  api: ExperimentSource
  vocab: Vocabulary
  run: ExperimentRun
  params: URLSearchParams
  onUpdate: (next: Record<string, string | null>) => void
}) {
  const load = useCallback(() => api.getExperiment(run.id), [api, run.id])
  const { data, error, loading, retry } = useResource(load)

  if (loading && !data) return <Loading message="Deney yükleniyor…" />
  if (error && !data) return <ErrorBox error={error} onRetry={retry} />
  if (!data) return null

  if (!data.metrics_available) {
    return (
      <>
        <Notice tone="error">
          <strong>Bu deney için rakam gösterilemiyor.</strong> {data.unavailable_reason}
        </Notice>
        <Empty
          title="Gösterilecek ölçüm yok"
          message="Deney dosyaları eksik, bozuk veya veri seti bulunamıyor. Bu ekran bu durumda örnek veya uydurma rakam üretmez."
        />
      </>
    )
  }

  const tab = (TABS.find((item) => item.key === params.get('gorunum'))?.key ?? 'karsilastirma') as Tab

  return (
    <div className="stack">
      {tab !== 'paylasim' ? <ExportActions detail={data} /> : null}
      <div className="tabs" role="tablist" aria-label="Görünüm">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={item.key === tab}
            className={item.key === tab ? 'tab active' : 'tab'}
            onClick={() =>
              onUpdate({
                gorunum: item.key === 'karsilastirma' ? null : item.key,
              })
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'karsilastirma' ? <ComparisonTab detail={data} /> : null}
      {tab === 'ornekler' ? (
        <SamplesTab api={api} vocab={vocab} detail={data} params={params} onUpdate={onUpdate} />
      ) : null}
      {tab === 'paylasim' ? (
        <ShareTab api={api} vocab={vocab} detail={data} params={params} onUpdate={onUpdate} />
      ) : null}
    </div>
  )
}

function ExportActions({
  detail,
  onPng,
  pngBusy,
}: {
  detail: ExperimentDetail
  onPng?: () => void
  pngBusy?: boolean
}) {
  return (
    <ExportBar
      onCsv={() => downloadText(buildCsv(detail), exportFileName(detail.run, 'csv'), 'text/csv')}
      onMarkdown={() => downloadText(buildMarkdown(detail), exportFileName(detail.run, 'md'), 'text/markdown')}
      onPng={onPng}
      busy={pngBusy}
    />
  )
}

function ComparisonTab({ detail }: { detail: ExperimentDetail }) {
  return (
    <div className="stack">
      <Warnings detail={detail} />
      <ComparisonTable detail={detail} />
      <p className="muted small">{detail.notes.tokens}</p>
      <p className="muted small">
        &quot;1.000 talebe ölçeklenen TAHMİN&quot; satırı ölçülmüş bir değer değildir: tamamlanan talep başına ölçülen
        ücretin 1.000 ile çarpımıdır ve küçük örneklemden kanıt sayılmaz. Bilinmeyen ücret veya eksik metrik sıfır
        olarak gösterilmez.
      </p>
      <div className="charts">
        <ChartSvg width={560} height={262} label="Tamamlanan talep başına ölçülen ücret">
          <BarChart
            x={20}
            y={0}
            width={520}
            height={262}
            title="Tamamlanan talep başına ölçülen ücret"
            subtitle="USD · yalnızca ücret"
            items={costBarItems(detail.strategies)}
          />
        </ChartSvg>
        <ChartSvg width={600} height={262} label="Uçtan uca karar süresi">
          <PairedBarChart
            x={20}
            y={0}
            width={560}
            height={262}
            title="Uçtan uca karar süresi"
            subtitle="milisaniye · ağ ve yeniden deneme dahil"
            firstLabel="p50"
            secondLabel="p95"
            items={latencyPairItems(detail.strategies)}
          />
        </ChartSvg>
      </div>
      <Reconciliation detail={detail} />
      <Conditions detail={detail} />
    </div>
  )
}

function SamplesTab({
  api,
  vocab,
  detail,
  params,
  onUpdate,
}: {
  api: ExperimentSource
  vocab: Vocabulary
  detail: ExperimentDetail
  params: URLSearchParams
  onUpdate: (next: Record<string, string | null>) => void
}) {
  const filter = (SAMPLE_FILTERS.find((item) => item.key === params.get('suzgec'))?.key ?? 'all') as SampleFilter
  const rows = filterSamples(detail.samples, filter)
  const sampleId = params.get('ornek')
  return (
    <div className="stack">
      <label className="field">
        <span>Süzgeç</span>
        <select
          value={filter}
          aria-label="Örnek süzgeci"
          onChange={(event) =>
            onUpdate({
              suzgec: event.target.value === 'all' ? null : event.target.value,
            })
          }
        >
          {SAMPLE_FILTERS.map((item) => (
            <option key={item.key} value={item.key}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <SampleTable
        detail={detail}
        rows={rows}
        vocab={vocab}
        selected={sampleId}
        onSelect={(id) => onUpdate({ ornek: id })}
      />
      {sampleId ? (
        <SampleInspector
          key={sampleId}
          api={api}
          runId={detail.run.id}
          sampleId={sampleId}
          vocab={vocab}
          onClose={() => onUpdate({ ornek: null })}
        />
      ) : (
        <p className="muted small">
          Ayrıntı için bir örnek kimliğine tıkla: tam metin, beklenen etiket ve üç stratejinin tahmini yan yana açılır.
        </p>
      )}
    </div>
  )
}

function ShareTab({
  api,
  vocab,
  detail,
  params,
  onUpdate,
}: {
  api: ExperimentSource
  vocab: Vocabulary
  detail: ExperimentDetail
  params: URLSearchParams
  onUpdate: (next: Record<string, string | null>) => void
}) {
  const common = detail.samples.filter((row) => row.in_common)
  const exampleId = params.get('ornek') ?? defaultExampleId(detail)
  const svgRef = useRef<SVGSVGElement>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function downloadPng() {
    if (!svgRef.current) return
    setBusy(true)
    setFailure(null)
    try {
      downloadBlob(await svgToPngBlob(svgRef.current, 2), exportFileName(detail.run, 'png'))
    } catch (problem) {
      setFailure(problem instanceof Error ? problem.message : 'PNG oluşturulamadı.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <ExportActions detail={detail} onPng={() => void downloadPng()} pngBusy={busy} />
      {failure ? <Notice tone="error">{failure}</Notice> : null}
      <label className="field">
        <span>Görselde karşılaştırılacak örnek talep</span>
        <select
          value={exampleId ?? ''}
          aria-label="Örnek talep"
          onChange={(event) => onUpdate({ ornek: event.target.value || null })}
        >
          {common.map((row) => (
            <option key={row.id} value={row.id}>
              {row.id} · {row.title}
              {row.disputed ? ' (tartışmalı etiket)' : ''}
            </option>
          ))}
        </select>
      </label>
      <div className="share-wrap">
        {exampleId ? (
          <ShareWithExample
            key={exampleId}
            api={api}
            vocab={vocab}
            detail={detail}
            exampleId={exampleId}
            svgRef={svgRef}
          />
        ) : (
          <ShareCard detail={detail} example={null} vocab={vocab} svgRef={svgRef} />
        )}
      </div>
    </div>
  )
}

function ShareWithExample({
  api,
  vocab,
  detail,
  exampleId,
  svgRef,
}: {
  api: ExperimentSource
  vocab: Vocabulary
  detail: ExperimentDetail
  exampleId: string
  svgRef: RefObject<SVGSVGElement | null>
}) {
  const load = useCallback(
    (): Promise<ExperimentSample> => api.getExperimentSample(detail.run.id, exampleId),
    [api, detail.run.id, exampleId],
  )
  const { data, error, loading, retry } = useResource(load)
  if (loading && !data) return <Loading message="Örnek talep yükleniyor…" />
  return (
    <>
      {error && !data ? (
        <Notice tone="error">
          Örnek talep yüklenemedi ({error.message}); görsel örnek olmadan gösteriliyor.{' '}
          <button type="button" className="link" onClick={retry}>
            Tekrar dene
          </button>
        </Notice>
      ) : null}
      <ShareCard detail={detail} example={data} vocab={vocab} svgRef={svgRef} />
    </>
  )
}

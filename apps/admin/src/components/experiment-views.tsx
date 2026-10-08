import { useCallback } from 'react'

import type { ExperimentSource } from '../lib/api'
import { confidenceText, questionText } from '../lib/decision'
import type {
  ExperimentDetail,
  ExperimentList,
  ExperimentRun,
  SampleRow,
  SampleStrategy,
} from '../lib/experiment-types'
import {
  NA,
  UNKNOWN,
  comparisonRows,
  formatCount,
  formatMs,
  formatUsd,
  providerLabel,
  routingLabel,
  runDate,
  runOptionText,
  scopeLabel,
  statusText,
  strategyModelLine,
  strategyTitle,
} from '../lib/experiments'
import { labelOf } from '../lib/format'
import type { Vocabulary } from '../lib/types'
import { useResource } from '../lib/use-resource'
import { Badge, ErrorBox, Loading, Notice } from './ui'

// --------------------------------------------------------------------------- seçici

function strategyTitleOf(info: ExperimentRun['strategies'][number]): string {
  return strategyTitle(info)
}

export function RunPicker({
  list,
  selected,
  onSelect,
}: {
  list: ExperimentList
  selected: string
  onSelect: (id: string) => void
}) {
  const run = list.runs.find((item) => item.id === selected) ?? list.runs[0]
  return (
    <section className="panel" aria-labelledby="run-picker">
      <h3 id="run-picker">Deney</h3>
      <label className="field">
        <span>Kayıtlı deney</span>
        <select value={run.id} onChange={(event) => onSelect(event.target.value)} aria-label="Kayıtlı deney">
          {list.runs.map((item) => (
            <option key={item.id} value={item.id}>
              {runOptionText(item)}
            </option>
          ))}
        </select>
      </label>
      <dl className="facts">
        <dt>Deney tarihi</dt>
        <dd>{runDate(run)}</dd>
        <dt>Örnek</dt>
        <dd>
          {scopeLabel(run)}
          {run.dataset ? ` · veri seti ${run.dataset.version ?? '?'}, bölüm: ${run.dataset.splits.join(', ')}` : ''}
        </dd>
        <dt>Stratejiler</dt>
        <dd>{run.strategies.map(strategyTitleOf).join(', ') || NA}</dd>
        <dt>Tamamlanma</dt>
        <dd>
          <Badge kind={run.status === 'complete' ? 'source-real' : 'priority-high'}>{statusText(run.status)}</Badge>
          {run.dataset && run.dataset.n_samples !== null
            ? ` ${run.dataset.n_completed ?? '?'}/${run.dataset.n_samples} örnek`
            : ''}
          {run.status_detail ? <span className="muted"> · {run.status_detail}</span> : null}
        </dd>
        <dt>Deney sürümü</dt>
        <dd>
          {run.hybrid_routing ? routingLabel(run.hybrid_routing) : 'Hibrit içermiyor'}
          {run.source_commit ? <span className="muted"> · kaynak commit {run.source_commit.slice(0, 7)}</span> : null}
          {run.live ? <span className="muted"> · gerçek sağlayıcı çağrıları</span> : null}
        </dd>
      </dl>
    </section>
  )
}

// --------------------------------------------------------------------------- uyarılar ve koşullar

export function Warnings({ detail }: { detail: ExperimentDetail }) {
  if (detail.warnings.length === 0) return null
  return (
    <div className="stack">
      {detail.warnings.map((warning) => (
        <Notice
          key={warning.code}
          tone={warning.code === 'small_sample' || warning.code === 'hybrid_v1' ? 'info' : 'error'}
        >
          {warning.text}
        </Notice>
      ))}
    </div>
  )
}

export function Conditions({ detail }: { detail: ExperimentDetail }) {
  const c = detail.conditions
  if (!c) return null
  return (
    <details className="panel">
      <summary>Deney koşulları (doğrudan kıyas için)</summary>
      <p className="muted small">{detail.notes.comparability}</p>
      <dl className="facts">
        <dt>Veri seti / bölüm</dt>
        <dd>
          {c.dataset_version} · {c.splits.join(', ')}
          {c.shuffle_seed !== null ? ` · karıştırma tohumu ${c.shuffle_seed}` : ''}
          {c.limit !== null ? ` · sınır ${c.limit} örnek` : ''}
          {c.final ? ' · nihai test' : ''}
        </dd>
        <dt>Çalıştırma</dt>
        <dd>
          eşzamanlılık {c.concurrency ?? '?'}, en çok {c.retry_max_attempts ?? '?'} deneme
          {c.python ? ` · Python ${c.python}` : ''}
        </dd>
        {c.strategies.map((info) => (
          <div key={info.name} className="contents">
            <dt>{strategyTitle(info)}</dt>
            <dd>
              {strategyModelLine(info)}
              {info.prompt_version ? <span className="muted"> · istem {info.prompt_version}</span> : null}
              {info.kind === 'hybrid' && info.thresholds ? (
                <div className="muted small">
                  Jev güven eşikleri:{' '}
                  {Object.entries(info.thresholds)
                    .map(([q, v]) => `${q}=${v}`)
                    .join(', ')}
                  {info.escalate_on
                    ? ` · LLM'e geçişi tetikleyebilen sorular: ${info.escalate_on.join(', ')}`
                    : ' · tetikleyebilen soru listesi kayıtta yok (v1: tüm sorular)'}
                </div>
              ) : null}
            </dd>
          </div>
        ))}
        <dt>Fiyatlar</dt>
        <dd>
          {c.prices
            .filter((p) => p.input_usd_per_mtok !== '0' || p.output_usd_per_mtok !== '0')
            .map((p) => (
              <div key={`${p.provider}-${p.model}`}>
                {p.model}: girdi {p.input_usd_per_mtok} / çıktı {p.output_usd_per_mtok} USD (1M token) · kontrol{' '}
                {p.checked_on}
              </div>
            ))}
        </dd>
      </dl>
    </details>
  )
}

// --------------------------------------------------------------------------- tablo ve harcama

export function ComparisonTable({ detail }: { detail: ExperimentDetail }) {
  const rows = comparisonRows(detail)
  return (
    <div className="table-wrap">
      <table className="compare" aria-label="Strateji karşılaştırması">
        <thead>
          <tr>
            <th scope="col">Ölçüt</th>
            {detail.strategies.map((r) => (
              <th scope="col" key={r.name}>
                {strategyTitle(r.info)}
                <div className="muted small nowrap">{strategyModelLine(r.info)}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              className={row.group === 'ucret' && row.key === 'cost_estimate_1000' ? 'estimate' : undefined}
            >
              <th scope="row">
                {row.label}
                {row.note ? <div className="muted small">{row.note}</div> : null}
              </th>
              {detail.strategies.map((r) => (
                <td key={r.name}>{row.cells[r.name] ?? NA}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Reconciliation({ detail }: { detail: ExperimentDetail }) {
  const rec = detail.reconciliation
  const budget = detail.budget
  if (!rec || !budget) {
    return <p className="muted small">Bu deney ücretsiz/mock olduğu için bütçe defteri bilgisi yok.</p>
  }
  return (
    <section className="panel" aria-labelledby="reconciliation">
      <h3 id="reconciliation">Harcama dökümü</h3>
      <dl className="facts">
        <dt>Bu çalıştırmadaki gerçek harcama</dt>
        <dd>{formatUsd(rec.run_known_spent_usd)} (bütçe defteri; tüm çağrılar)</dd>
        <dt>Karşılaştırılan örneklerde</dt>
        <dd>{formatUsd(rec.compared_known_usd)}</dd>
        <dt>Karşılaştırma dışı harcama</dt>
        <dd>{formatUsd(rec.outside_comparison_usd)} (yarım/ortak olmayan örnekler; toplamdan gizlenmez)</dd>
        <dt>En kötü durum bedeliyle sayılan</dt>
        <dd>{formatUsd(rec.conservative_spent_usd)} (bilinmeyen ücretler; gerçek harcama olmayabilir)</dd>
        <dt>Defter</dt>
        <dd>
          {budget.budget_id} · sınır {formatUsd(budget.max_cost_usd)} · kalan {formatUsd(budget.remaining_usd)}
        </dd>
      </dl>
      <p className="muted small">
        Bu ekran defteri yalnızca okur; hiçbir değer değiştirilmez ve hiçbir model çağrısı yapılmaz.
      </p>
    </section>
  )
}

// --------------------------------------------------------------------------- örnekler

function cellText(cell: SampleRow['strategies'][string], vocab: Vocabulary): string {
  if (!cell) return 'kayıt yok'
  if (cell.failed) return 'karar üretilemedi'
  const category =
    cell.category === null || cell.category === 'unclear' ? 'Belirsiz' : labelOf(vocab.categories, cell.category)
  const priority = cell.priority === null ? 'Belirsiz' : labelOf(vocab.priorities, cell.priority)
  const mark = (ok: boolean | null) => (ok === null ? '' : ok ? ' (doğru)' : ' (yanlış)')
  return `${category}${mark(cell.category_ok)} · ${priority}${mark(cell.priority_ok)}`
}

export function SampleTable({
  detail,
  rows,
  vocab,
  selected,
  onSelect,
}: {
  detail: ExperimentDetail
  rows: SampleRow[]
  vocab: Vocabulary
  selected: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="table-wrap">
      <table aria-label="Örnek bazında karşılaştırma">
        <thead>
          <tr>
            <th scope="col">Örnek</th>
            <th scope="col">Beklenen etiket</th>
            {detail.strategies.map((r) => (
              <th scope="col" key={r.name}>
                {strategyTitle(r.info)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className={row.id === selected ? 'selected' : undefined}>
              <td>
                <button
                  type="button"
                  className="link"
                  onClick={() => onSelect(row.id)}
                  aria-label={`${row.id} örneğini incele`}
                >
                  {row.id}
                </button>{' '}
                {row.title}
                <div className="row wrap">
                  {row.disputed ? <Badge kind="priority-high">Tartışmalı etiket</Badge> : null}
                  {!row.in_common ? <Badge>Karşılaştırma dışı</Badge> : null}
                </div>
              </td>
              <td>
                {labelOf(vocab.categories, row.gold.category) || row.gold.category} ·{' '}
                {labelOf(vocab.priorities, row.gold.priority)}
              </td>
              {detail.strategies.map((r) => (
                <td key={r.name}>{cellText(row.strategies[r.name] ?? null, vocab)}</td>
              ))}
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={2 + detail.strategies.length} className="muted">
                Bu süzgeçte örnek yok.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

function StrategyColumn({ strategy, vocab }: { strategy: SampleStrategy; vocab: Vocabulary }) {
  const title = strategyTitle(strategy.info)
  if (!strategy.present) {
    return (
      <section className="panel" aria-label={title}>
        <h3>{title}</h3>
        <p className="muted">Bu örnek için kayıt yok.</p>
      </section>
    )
  }
  const mark = (ok: boolean | null) =>
    ok === null ? null : <Badge kind={ok ? 'source-real' : 'priority-high'}>{ok ? 'doğru' : 'yanlış'}</Badge>
  return (
    <section className="panel" aria-label={title}>
      <h3>{title}</h3>
      <p className="muted small">{strategyModelLine(strategy.info)}</p>
      {strategy.failed ? (
        <Notice tone="error">Karar üretilemedi{strategy.error ? `: ${strategy.error}` : ''}</Notice>
      ) : null}
      <dl className="facts">
        <dt>Kategori</dt>
        <dd>
          {strategy.category === null || strategy.category === 'unclear'
            ? 'Belirsiz'
            : labelOf(vocab.categories, strategy.category)}{' '}
          {mark(strategy.category_ok)}
        </dd>
        <dt>Öncelik</dt>
        <dd>
          {strategy.priority === null ? 'Belirsiz' : labelOf(vocab.priorities, strategy.priority)}{' '}
          {mark(strategy.priority_ok)}
        </dd>
        <dt>İnceleme</dt>
        <dd>{strategy.review_required === null ? NA : strategy.review_required ? 'Gerekiyor' : 'Gerekmiyor'}</dd>
        <dt>Süre</dt>
        <dd>{formatMs(strategy.latency_ms)}</dd>
        <dt>Ücret</dt>
        <dd>
          {formatUsd(strategy.cost_known_usd)}
          {strategy.calls_with_unknown_cost ? ` + ${strategy.calls_with_unknown_cost} çağrının ücreti bilinmiyor` : ''}
        </dd>
        <dt>Token</dt>
        <dd>
          {strategy.usage.map((u) => (
            <div key={`${u.provider}-${u.model}`}>
              {providerLabel(u.provider)}: {formatCount(u.input_tokens)} giriş / {formatCount(u.output_tokens)} çıkış
              {u.output_tokens_free ? ' (çıktı ücretsiz)' : ''}
            </div>
          ))}
        </dd>
        {strategy.info.kind === 'hybrid' ? (
          <>
            <dt>LLM&apos;e aktarılan sorular</dt>
            <dd>
              {strategy.escalated_questions.length > 0
                ? strategy.escalated_questions.map(questionText).join(' · ')
                : "LLM'e geçiş olmadı"}
            </dd>
          </>
        ) : null}
      </dl>
      <details>
        <summary>Soru bazında yargılar ve güven değerleri ({strategy.judgments.length})</summary>
        <p className="muted small">
          Güven değerleri farklı kavramlardır ve birbirine eşdeğer sayılmaz: Jev&apos;in kendi güveni, olasılıktan bizim
          türettiğimiz marj ve modelin kendi bildirdiği (kalibre olmayan) güven. Modelin yazmadığı bir gerekçe
          gösterilmez.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Soru</th>
                <th scope="col">Cevap</th>
                <th scope="col">Güven (tür)</th>
                <th scope="col">Kaynak</th>
              </tr>
            </thead>
            <tbody>
              {strategy.judgments.map((j, index) => (
                <tr key={`${j.question}-${j.source}-${index}`}>
                  <td>{questionText(j.question)}</td>
                  <td>
                    {j.answer === null
                      ? 'Belirsiz'
                      : typeof j.answer === 'boolean'
                        ? j.answer
                          ? 'Evet'
                          : 'Hayır'
                        : String(j.answer)}
                  </td>
                  <td>{confidenceText(j)}</td>
                  <td>
                    {j.source ?? NA}
                    {j.adopted ? '' : ' (karara alınmadı)'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details>
        <summary>Çağrılar ({strategy.calls.length})</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Sağlayıcı</th>
                <th scope="col">Deneme</th>
                <th scope="col">Durum</th>
                <th scope="col">Süre</th>
                <th scope="col">Token</th>
                <th scope="col">Ücret</th>
                <th scope="col">Sorular</th>
              </tr>
            </thead>
            <tbody>
              {strategy.calls.map((call, index) => (
                <tr key={index}>
                  <td>{providerLabel(call.provider ?? '?')}</td>
                  <td>{call.attempt ?? NA}</td>
                  <td>{call.status ?? UNKNOWN}</td>
                  <td>{call.duration_ms === null ? UNKNOWN : `${call.duration_ms} ms`}</td>
                  <td>
                    {call.input_tokens === null ? UNKNOWN : formatCount(call.input_tokens)} /{' '}
                    {call.output_tokens === null ? UNKNOWN : formatCount(call.output_tokens)}
                  </td>
                  <td>{formatUsd(call.cost_usd)}</td>
                  <td>{(call.questions ?? []).map(questionText).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

export function SampleInspector({
  api,
  runId,
  sampleId,
  vocab,
  onClose,
}: {
  api: ExperimentSource
  runId: string
  sampleId: string
  vocab: Vocabulary
  onClose: () => void
}) {
  const load = useCallback(() => api.getExperimentSample(runId, sampleId), [api, runId, sampleId])
  const { data, error, loading, retry } = useResource(load)

  if (loading && !data) return <Loading message="Örnek yükleniyor…" />
  if (error && !data) return <ErrorBox error={error} onRetry={retry} />
  if (!data) return null
  const { sample } = data

  return (
    <section className="stack" aria-label={`${sample.id} örnek ayrıntısı`}>
      <div className="row wrap">
        <h2>
          {sample.id} · {sample.title}
        </h2>
        <div className="spacer" />
        <button type="button" className="btn btn-small" onClick={onClose}>
          Kapat
        </button>
      </div>
      <div className="panel">
        <p className="description">{sample.description}</p>
        <dl className="facts">
          <dt>Konum</dt>
          <dd>{sample.location}</dd>
          <dt>Beklenen etiket</dt>
          <dd>
            Kategori: {labelOf(vocab.categories, sample.gold.category) || sample.gold.category} · Öncelik:{' '}
            {labelOf(vocab.priorities, sample.gold.priority)} · İnceleme beklenir:{' '}
            {sample.gold.expected_review ? 'evet' : 'hayır'}
          </dd>
          <dt>Etiket durumu</dt>
          <dd>
            {sample.label_status === 'single_annotator_unreviewed'
              ? 'tek kişiyce yazıldı, gözden geçirilmedi'
              : sample.label_status}
            {' · '}bölüm: {sample.split} · yazım: {sample.variant}
          </dd>
        </dl>
        {sample.disputed ? (
          <Notice tone="error">
            <strong>Tartışmalı etiket ({sample.disputed.status}).</strong> {sample.disputed.note} Etiketler ve geçmiş
            deney sonuçları değiştirilmedi.
          </Notice>
        ) : null}
      </div>
      <div className="columns three">
        {data.strategies.map((strategy) => (
          <StrategyColumn key={strategy.name} strategy={strategy} vocab={vocab} />
        ))}
      </div>
    </section>
  )
}

// --------------------------------------------------------------------------- dışa aktarma

export function ExportBar({
  onCsv,
  onMarkdown,
  onPng,
  pngDisabled,
  busy,
}: {
  onCsv: () => void
  onMarkdown: () => void
  onPng?: () => void
  pngDisabled?: boolean
  busy?: boolean
}) {
  return (
    <div className="row wrap" role="group" aria-label="Dışa aktar">
      {onPng ? (
        <button type="button" className="btn btn-primary" onClick={onPng} disabled={pngDisabled || busy}>
          {busy ? 'Hazırlanıyor…' : 'PNG indir'}
        </button>
      ) : null}
      <button type="button" className="btn" onClick={onCsv}>
        CSV indir
      </button>
      <button type="button" className="btn" onClick={onMarkdown}>
        Markdown tablo indir
      </button>
      <span className="muted small">Dışa aktarma yüklü verilerden üretilir; model çağrısı yapmaz.</span>
    </div>
  )
}

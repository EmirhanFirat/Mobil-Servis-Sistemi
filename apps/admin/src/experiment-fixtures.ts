import type {
  ExperimentDetail,
  ExperimentList,
  ExperimentRun,
  ExperimentSample,
  ExperimentStrategyInfo,
  Proportion,
  SampleCell,
  SampleRow,
  SampleStrategy,
  StrategyResult,
} from './lib/experiment-types'

/** Gerçek ilk denemenin (2026-10-02, 5 sentetik geliştirme örneği) sayıları; yalnızca test verisi. */

export const RUN_ID = '20261002T162249Z-v1-dev'

function prop(successes: number, n: number): Proportion {
  return { successes, n, value: n === 0 ? null : successes / n, wilson95: [0.1, 1] }
}

export const jevInfo: ExperimentStrategyInfo = {
  name: 'jev_only',
  kind: 'jev_only',
  is_mock: false,
  provider: 'jev',
  model: 'jev-1.13.0',
  prompt_version: 'jev-sorular-v1-8c2683f3f49e',
  temperature: null,
  jev: null,
  llm: null,
  thresholds: null,
  escalate_on: null,
  llm_min_self_reported: null,
  routing_version: null,
}

export const llmInfo: ExperimentStrategyInfo = {
  ...jevInfo,
  name: 'llm_only',
  kind: 'llm_only',
  provider: 'anthropic',
  model: 'claude-haiku-4-5-20251001',
  prompt_version: 'llm-istem-v1-e4fabd817c1e',
  temperature: 0,
}

export const hybridInfo: ExperimentStrategyInfo = {
  ...jevInfo,
  name: 'hybrid',
  kind: 'hybrid',
  provider: null,
  model: null,
  prompt_version: null,
  jev: {
    provider: 'jev',
    model: 'jev-1.13.0',
    prompt_version: 'jev-sorular-v1-x',
    temperature: null,
  },
  llm: {
    provider: 'anthropic',
    model: 'claude-haiku-4-5-20251001',
    prompt_version: 'llm-istem-v1-x',
    temperature: 0,
  },
  thresholds: {
    category: 0.6,
    priority: 0.6,
    missing_location: 0.6,
    missing_detail: 0.6,
    missing_contact: 0.6,
    missing_timing: 0.6,
  },
  escalate_on: null,
}

export function makeRun(overrides: Partial<ExperimentRun> = {}): ExperimentRun {
  return {
    id: RUN_ID,
    created_at: '2026-10-02T16:22:49.891057+00:00',
    source_commit: '09584e99f1614df2ec202b61dd1d422dbf4ff71d',
    git_dirty: false,
    dataset: {
      version: 'v1',
      sha256_short: '297a1dddf2347be2',
      splits: ['dev'],
      n_samples: 5,
      n_completed: 5,
      source: 'synthetic',
      label_status: 'single_annotator_unreviewed',
      matches_current: true,
    },
    strategies: [jevInfo, llmInfo, hybridInfo],
    status: 'complete',
    status_detail: null,
    live: true,
    hybrid_routing: {
      version: 'hibrit-yonlendirme-v1',
      recorded: false,
      description: "Tüm sorulara aynı Jev güven eşiği; güvenilmeyen HER soru LLM'e geçerdi.",
    },
    scope_label: '5 sentetik geliştirme örneği — bağlantı denemesi',
    files: { predictions: true, metrics: true, report: true },
    ...overrides,
  }
}

export function makeList(runs: ExperimentRun[] = [makeRun()], found = true): ExperimentList {
  return { runs_dir_found: found, runs }
}

function result(
  info: ExperimentStrategyInfo,
  fields: {
    prioritySuccesses: number
    p50: number
    p95: number
    known: string
    perCompleted: string
    estimate: string
    inputTokens: number
    outputTokens: number
    calls: number
    providers: StrategyResult['usage']['providers']
    hybrid?: StrategyResult['hybrid']
  },
): StrategyResult {
  return {
    name: info.name,
    info,
    n: 5,
    n_failed: 0,
    metrics: {
      category_accuracy: prop(5, 5),
      category_macro_f1: 1,
      priority_accuracy: prop(fields.prioritySuccesses, 5),
      high_priority_recall: prop(1, 1),
      high_priority_missed: [],
      review_rate: prop(0, 5),
      automated_rate: prop(5, 5),
      automated_category_accuracy: prop(5, 5),
      automated_priority_accuracy: prop(fields.prioritySuccesses, 5),
      latency_p50_ms: fields.p50,
      latency_p95_ms: fields.p95,
    },
    cost: {
      known_usd: fields.known,
      calls_with_unknown_cost: 0,
      total_usd: fields.known,
      per_completed_usd: fields.perCompleted,
      estimate_per_1000_usd: fields.estimate,
    },
    usage: {
      providers: fields.providers,
      calls: fields.calls,
      retries: 0,
      call_errors: 0,
      input_tokens: fields.inputTokens,
      output_tokens: fields.outputTokens,
      calls_without_usage: 0,
    },
    hybrid: fields.hybrid ?? null,
  }
}

const jevUsage = {
  provider: 'jev',
  model: 'jev-1.13.0',
  is_mock: false,
  calls: 5,
  retries: 0,
  call_errors: 0,
  input_tokens: 4603,
  output_tokens: 902,
  calls_without_input_usage: 0,
  calls_without_output_usage: 0,
  usage_estimated_calls: 0,
  output_tokens_free: true,
  cost_known_usd: '0.000193326',
  calls_with_unknown_cost: 0,
}

const llmUsage = {
  provider: 'anthropic',
  model: 'claude-haiku-4-5-20251001',
  is_mock: false,
  calls: 5,
  retries: 0,
  call_errors: 0,
  input_tokens: 9840,
  output_tokens: 974,
  calls_without_input_usage: 0,
  calls_without_output_usage: 0,
  usage_estimated_calls: 0,
  output_tokens_free: false,
  cost_known_usd: '0.01471',
  calls_with_unknown_cost: 0,
}

const gold = (category: string, priority: string) => ({
  category,
  priority,
  missing_info: [],
  expected_review: false,
})

function cell(category: string, priority: string, categoryOk = true, priorityOk = true): SampleCell {
  return {
    failed: false,
    category,
    priority,
    category_ok: categoryOk,
    priority_ok: priorityOk,
    review_required: false,
    latency_ms: 300,
    cost_known_usd: '0.0000386',
    calls_with_unknown_cost: 0,
  }
}

function row(
  id: string,
  title: string,
  category: string,
  priority: string,
  goldPriority = priority,
  disputed = false,
): SampleRow {
  const priorityOk = priority === goldPriority
  return {
    id,
    title,
    split: 'dev',
    variant: 'kisa',
    tags: [],
    gold: gold(category, goldPriority),
    disputed: disputed ? { status: 'gözden geçirme bekliyor', note: 'Asansör kapısı örneği: rehber belirsiz.' } : null,
    in_common: true,
    strategies: {
      jev_only: cell(category, priority, true, priorityOk),
      llm_only: cell(category, priority, true, priorityOk),
      hybrid: cell(category, priority, true, priorityOk),
    },
  }
}

export function makeDetail(overrides: Partial<ExperimentDetail> = {}): ExperimentDetail {
  return {
    run: makeRun(),
    metrics_available: true,
    unavailable_reason: null,
    conditions: {
      dataset_version: 'v1',
      splits: ['dev'],
      shuffle_seed: 4,
      final: false,
      limit: 5,
      concurrency: 1,
      retry_max_attempts: 3,
      strategies: [jevInfo, llmInfo, hybridInfo],
      prices: [
        {
          provider: 'jev',
          model: 'jev-1.13.0',
          input_usd_per_mtok: '0.042',
          output_usd_per_mtok: '0',
          source_url: 'https://docs.typesafe.ai/models',
          checked_on: '2026-10-02',
        },
        {
          provider: 'anthropic',
          model: 'claude-haiku-4-5-20251001',
          input_usd_per_mtok: '1',
          output_usd_per_mtok: '5',
          source_url: 'https://platform.claude.com/docs/en/about-claude/pricing',
          checked_on: '2026-10-02',
        },
      ],
      python: '3.12.7',
    },
    budget: {
      budget_id: 'ilk-deneme',
      max_cost_usd: '0.10',
      known_spent_usd: '0.021376652',
      conservative_spent_usd: '0',
      conservative_charges: 0,
      calls: 20,
      prior_spent_usd: '0',
      prior_unresolved_reserved_usd: '0',
      total_spent_usd: '0.021376652',
      remaining_usd: '0.078623348',
    },
    common: { n: 5, sample_ids: ['s003', 's009', 's020', 's023', 's051'], excluded: [] },
    strategies: [
      result(jevInfo, {
        prioritySuccesses: 4,
        p50: 314.763,
        p95: 466.6982,
        known: '0.000193326',
        perCompleted: '0.0000386652',
        estimate: '0.0386652',
        inputTokens: 4603,
        outputTokens: 902,
        calls: 5,
        providers: [jevUsage],
      }),
      result(llmInfo, {
        prioritySuccesses: 4,
        p50: 1569.493,
        p95: 2266.1762,
        known: '0.01471',
        perCompleted: '0.002942',
        estimate: '2.942',
        inputTokens: 9840,
        outputTokens: 974,
        calls: 5,
        providers: [llmUsage],
      }),
      result(hybridInfo, {
        prioritySuccesses: 4,
        p50: 1122.632,
        p95: 1146.2248,
        known: '0.006473326',
        perCompleted: '0.0012946652',
        estimate: '1.2946652',
        inputTokens: 9703,
        outputTokens: 1138,
        calls: 10,
        providers: [
          {
            ...llmUsage,
            input_tokens: 5100,
            output_tokens: 236,
            cost_known_usd: '0.00628',
          },
          jevUsage,
        ],
        hybrid: {
          escalated: prop(5, 5),
          trigger_questions: { missing_contact: 5 },
          jev_stage_calls: 5,
          llm_stage_calls: 5,
        },
      }),
    ],
    reconciliation: {
      compared_known_usd: '0.021376652',
      run_known_spent_usd: '0.021376652',
      outside_comparison_usd: '0',
      conservative_spent_usd: '0',
    },
    samples: [
      row('s003', 'lavabo akitiyor', 'plumbing', 'high'),
      row('s009', 'ampul yanmiyor', 'electrical', 'normal'),
      row('s020', 'Duş alanı temizlenmemiş', 'cleaning', 'normal'),
      row('s023', 'Asansör bozuk', 'other', 'high', 'normal', true),
      row('s051', 'klozet su akitiyor', 'plumbing', 'normal'),
    ],
    warnings: [
      {
        code: 'small_sample',
        text: 'Küçük örneklem (5 örnek): bu deney bağlantıyı, biçimi ve çağrı kayıtlarını doğrular; doğruluk, güvenilirlik veya maliyet tasarrufu sonucu çıkarılamaz.',
      },
      {
        code: 'hybrid_v1',
        text: "Bu deney hibrit yönlendirme v1 ile alındı (kayıtta sürüm alanı yok). Güncel kod (v2) ile alınmış gibi okunmamalıdır; v2'nin daha iyi olduğuna dair henüz gerçek ölçüm yoktur.",
      },
      {
        code: 'disputed_labels',
        text: 'Tartışmalı etiketli örnek: s023 (bağımsız ikinci değerlendirme bekliyor). Etiketler ve bu deneyin sonuçları değiştirilmedi.',
      },
    ],
    notes: {
      comparability:
        'Bu ekran yalnızca AYNI deneydeki stratejileri karşılaştırır. Farklı deneyler otomatik olarak doğrudan kıyaslanmaz.',
      tokens: "Farklı sağlayıcıların tokenizer'ları eşdeğer değildir; token sayıları birebir karşılaştırılmamalıdır.",
    },
    ...overrides,
  }
}

function sampleStrategy(
  info: ExperimentStrategyInfo,
  category: string,
  priority: string,
  extra: Partial<SampleStrategy> = {},
): SampleStrategy {
  return {
    name: info.name,
    info,
    present: true,
    failed: false,
    error: null,
    category,
    priority,
    missing_info: [],
    review_required: false,
    review_reasons: [],
    latency_ms: 320,
    is_mock: false,
    providers: [],
    model_versions: [],
    category_ok: true,
    priority_ok: false,
    judgments: [
      {
        question: 'category',
        answer: category,
        probabilities: { other: 1 },
        confidence: info.kind === 'llm_only' ? 0.95 : 1,
        confidence_kind: info.kind === 'llm_only' ? 'self_reported' : 'jev_confidence',
        n_options: 6,
        source: info.kind === 'llm_only' ? 'anthropic' : 'jev',
        adopted: true,
      },
      {
        question: 'missing_contact',
        answer: true,
        probabilities: { yes: 0.76, no: 0.24 },
        confidence: 0.52,
        confidence_kind: 'derived_margin',
        n_options: 2,
        source: 'jev',
        adopted: info.kind !== 'hybrid',
      },
    ],
    calls: [
      {
        provider: info.provider ?? 'jev',
        model: info.model ?? 'jev-1.13.0',
        attempt: 1,
        status: 'ok',
        duration_ms: 300,
        input_tokens: 921,
        output_tokens: 179,
        usage_estimated: false,
        cost_usd: '0.000038682',
        questions: ['category', 'priority'],
        is_mock: false,
      },
    ],
    usage: [jevUsage],
    cost_known_usd: '0.000038682',
    calls_with_unknown_cost: 0,
    escalated_questions: [],
    ...extra,
  }
}

export function makeSample(): ExperimentSample {
  return {
    run_id: RUN_ID,
    sample: {
      id: 's023',
      title: 'Asansör bozuk',
      description: 'Asansör kapısı kapanmıyor, kata gelince açılmıyor.',
      location: 'C Blok zemin kat',
      split: 'dev',
      variant: 'kisa',
      tags: [],
      source: 'synthetic',
      label_status: 'single_annotator_unreviewed',
      gold: gold('other', 'normal'),
      disputed: {
        status: 'gözden geçirme bekliyor',
        note: 'Asansör kapısı örneği: rehber belirsiz.',
      },
    },
    strategies: [
      sampleStrategy(jevInfo, 'other', 'high'),
      sampleStrategy(llmInfo, 'other', 'high', { latency_ms: 2436, usage: [llmUsage] }),
      sampleStrategy(hybridInfo, 'other', 'high', {
        latency_ms: 1151,
        usage: [llmUsage, jevUsage],
        escalated_questions: ['missing_contact'],
      }),
    ],
  }
}

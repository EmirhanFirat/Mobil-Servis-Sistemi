import { labelOf } from './format'
import type {
  ApplyOutcome,
  Decision,
  DecisionJob,
  DecisionJudgment,
  DecisionStrategy,
  JobOutcome,
  Vocabulary,
} from './types'

const STRATEGY_LABELS: Record<DecisionStrategy, string> = {
  rule_based: 'Kural tabanlı',
  llm_only: 'Yalnızca LLM',
  jev_only: 'Yalnızca Jev',
  hybrid: 'Hibrit (Jev + LLM)',
}

export type SourceKind = 'rule' | 'mock' | 'real'

export interface DecisionSource {
  kind: SourceKind
  /** Rozette görünen kısa ad. */
  title: string
  detail: string
}

/**
 * Kararın kaynağı. Mock bir karar GERÇEK model ölçümü gibi gösterilmez: rozet ve metin açıkça
 * "mock" der; kurallı taban model çağırmaz.
 */
export function decisionSource(decision: Decision): DecisionSource {
  const strategy = STRATEGY_LABELS[decision.strategy] ?? decision.strategy
  if (decision.strategy === 'rule_based') {
    return { kind: 'rule', title: 'Kural tabanlı', detail: 'Kurallarla üretildi; model çağrısı yok.' }
  }
  const models = decision.model_versions.length > 0 ? decision.model_versions.join(', ') : '—'
  if (decision.is_mock) {
    return {
      kind: 'mock',
      title: 'MOCK — gerçek model değil',
      detail: `${strategy} stratejisi sahte (mock) sağlayıcılarla çalıştı: ${models}.`,
    }
  }
  return { kind: 'real', title: 'Gerçek model', detail: `${strategy}: ${models}.` }
}

const APPLY_TEXT: Record<ApplyOutcome, string> = {
  applied: 'Talebe uygulandı.',
  skipped_not_new: 'Uygulanmadı: model çalışırken talep artık “Yeni” durumunda değildi.',
  skipped_human_edit: 'Uygulanmadı: model çalışırken bir yönetici alanları elle düzeltmişti.',
}

export function applyOutcomeText(outcome: ApplyOutcome): string {
  return APPLY_TEXT[outcome] ?? outcome
}

const JOB_OUTCOME_TEXT: Record<JobOutcome, string> = {
  decided: 'tamamlandı',
  skipped_not_new: 'model çağrılmadı: talep artık “Yeni” değildi',
  skipped_human_edit: 'model çağrılmadı: alanlar elle düzeltilmişti',
  failed_provider: 'sağlayıcı yanıt vermedi (denemeler tükendi)',
  failed_error: 'beklenmeyen hata (denemeler tükendi)',
  failed_worker_lost: 'işleyici kayboldu (denemeler tükendi)',
}

export interface JobLine {
  tone: 'info' | 'success' | 'error'
  text: string
}

/** Karar işinin durumu: bekliyor/işleniyor/bitti/başarısız. Başarısızlık görünür olmalı. */
export function jobLine(job: DecisionJob): JobLine {
  const attempts = `${job.attempts}/${job.max_attempts} deneme`
  switch (job.status) {
    case 'pending':
      return {
        tone: 'info',
        text:
          job.attempts > 0
            ? `Karar işi yeniden denenmek üzere bekliyor (${attempts}).`
            : 'Karar işi kuyrukta bekliyor; işleyici (worker) çalışınca karar üretilecek.',
      }
    case 'running':
      return { tone: 'info', text: `Karar işi işleniyor (${attempts}).` }
    case 'succeeded':
      return {
        tone: 'success',
        text: `Karar işi ${job.outcome ? JOB_OUTCOME_TEXT[job.outcome] : 'tamamlandı'}.`,
      }
    default:
      return {
        tone: 'error',
        text: `Karar işi başarısız: ${job.outcome ? JOB_OUTCOME_TEXT[job.outcome] : 'bilinmeyen neden'}. Talep insan incelemesine alındı.`,
      }
  }
}

const REASON_TEXT: Record<string, string> = {
  category_unclear: 'Kategori belirsiz',
  priority_unclear: 'Aciliyet belirsiz',
  location_missing: 'Konum eksik',
  detail_missing: 'Açıklama yetersiz',
  possible_prompt_injection: 'Talimat enjeksiyonu şüphesi',
  multiple_issues: 'Birden çok sorun içeriyor',
  llm_unavailable: 'LLM yanıt vermedi',
  location_unknown: 'Konumun yeterli olup olmadığı belirsiz (karar verilemedi)',
  detail_unknown: 'Açıklamanın yeterli olup olmadığı belirsiz (karar verilemedi)',
}

export function reasonText(code: string): string {
  if (code.startsWith('safety:')) return `Güvenlik terimi: ${code.slice('safety:'.length)}`
  return REASON_TEXT[code] ?? code
}

const QUESTION_TEXT: Record<string, string> = {
  category: 'Kategori',
  priority: 'Aciliyet',
  missing_location: 'Konum eksik mi?',
  missing_detail: 'Açıklama yetersiz mi?',
  missing_contact: 'İletişim bilgisi eksik mi?',
  missing_timing: 'Başlangıç zamanı eksik mi?',
}

export function questionText(question: string): string {
  return QUESTION_TEXT[question] ?? question
}

const QUESTION_ORDER = [
  'category',
  'priority',
  'missing_location',
  'missing_detail',
  'missing_contact',
  'missing_timing',
]

/**
 * Karara girmiş KESİN yanıtı olmayan sorular (soru sırasıyla): yalnızca sorulan sorular sayılır.
 * Benimsenmeyen, belirsiz ("unclear") ve boş yanıtlar çözülmüş sayılmaz. Bu sorular için
 * "eksik değil" demek yanlıştır: bilinmiyorlar (ör. hibritte Jev'in emin olmadığı bilgi amaçlı
 * soru LLM'e aktarılmaz; kural tabanlı strateji iletişim/zamanı hiç değerlendirmez).
 * Python tarafındaki `unresolved_questions` ile aynı kural.
 */
export function unresolvedQuestions(judgments: DecisionJudgment[]): string[] {
  const resolved = new Set(
    judgments
      .filter((j) => j.adopted && j.answer !== null && j.answer !== undefined && j.answer !== 'unclear')
      .map((j) => j.question),
  )
  const asked = new Set(judgments.map((j) => j.question))
  return QUESTION_ORDER.filter((question) => asked.has(question) && !resolved.has(question))
}

/** Yargının cevabı Türkçe adıyla; "unclear" ve boş cevap açıkça belirsiz diye gösterilir. */
export function answerText(judgment: DecisionJudgment, vocab: Vocabulary): string {
  const { answer, question } = judgment
  if (answer === null || answer === undefined || answer === 'unclear') return 'Belirsiz'
  if (typeof answer === 'boolean') return answer ? 'Evet' : 'Hayır'
  if (question === 'category') return labelOf(vocab.categories, answer)
  if (question === 'priority') return labelOf(vocab.priorities, answer)
  return answer
}

const CONFIDENCE_KIND_TEXT: Record<string, string> = {
  jev_confidence: 'Jev güveni',
  derived_margin: 'olasılıktan türetilmiş',
  self_reported: 'modelin kendi yazdığı, kalibre değil',
}

/** Güven değeri türüyle birlikte: farklı türler birbirine eşdeğer sayılmasın. */
export function confidenceText(judgment: DecisionJudgment): string {
  if (judgment.confidence === null || judgment.confidence === undefined) return 'yok'
  const value = judgment.confidence.toFixed(2).replace('.', ',')
  const kind = judgment.confidence_kind ? CONFIDENCE_KIND_TEXT[judgment.confidence_kind] : null
  return kind ? `${value} (${kind})` : value
}

/** Çağrı sayısı ve ücret; bilinmeyen ücret sıfır sayılmaz, ayrıca belirtilir. */
export function costText(decision: Decision): string {
  if (decision.calls_total === 0) return 'Model çağrısı yok.'
  const known = decision.cost_known_usd ?? '0'
  const unknown =
    decision.calls_with_unknown_cost > 0
      ? `; ${decision.calls_with_unknown_cost} çağrının ücreti bilinmiyor (sıfır sayılmadı)`
      : ''
  return `${decision.calls_total} çağrı; bilinen ücret ${known.replace('.', ',')} USD${unknown}.`
}

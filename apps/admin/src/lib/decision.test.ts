import { describe, expect, it } from 'vitest'

import { makeDecision, vocab } from '../test-utils'
import {
  answerText,
  applyOutcomeText,
  confidenceText,
  costText,
  decisionSource,
  jobLine,
  reasonText,
} from './decision'
import type { DecisionJob, DecisionJudgment } from './types'

function makeJob(overrides: Partial<DecisionJob> = {}): DecisionJob {
  return {
    strategy: 'rule_based',
    status: 'pending',
    outcome: null,
    attempts: 0,
    max_attempts: 3,
    last_error: null,
    created_at: '2026-10-02T10:00:00Z',
    finished_at: null,
    ...overrides,
  }
}

function judgment(overrides: Partial<DecisionJudgment> = {}): DecisionJudgment {
  return {
    question: 'category',
    answer: 'plumbing',
    probabilities: null,
    confidence: 0.93,
    confidence_kind: 'self_reported',
    n_options: 6,
    source: 'anthropic',
    adopted: true,
    ...overrides,
  }
}

describe('decisionSource', () => {
  it('kural tabanlı karar model çağırmaz', () => {
    const source = decisionSource(makeDecision())

    expect(source.kind).toBe('rule')
    expect(source.detail).toContain('model çağrısı yok')
  })

  it('mock karar açıkça mock olarak işaretlenir ve gerçek model gibi gösterilmez', () => {
    const source = decisionSource(
      makeDecision({ strategy: 'hybrid', is_mock: true, model_versions: ['mock-jev-1', 'mock-llm-1'] }),
    )

    expect(source.kind).toBe('mock')
    expect(source.title).toContain('MOCK')
    expect(source.title).toContain('gerçek model değil')
    expect(source.detail).toContain('mock-jev-1')
  })

  it('gerçek model kararı model sürümüyle gösterilir', () => {
    const source = decisionSource(
      makeDecision({ strategy: 'llm_only', is_mock: false, model_versions: ['claude-haiku-4-5-20251001'] }),
    )

    expect(source.kind).toBe('real')
    expect(source.detail).toContain('claude-haiku-4-5-20251001')
    expect(source.detail).toContain('Yalnızca LLM')
  })
})

describe('uygulama ve iş durumu', () => {
  it('uygulanmama nedenleri insan düzeltmesini ve durum değişimini anlatır', () => {
    expect(applyOutcomeText('applied')).toBe('Talebe uygulandı.')
    expect(applyOutcomeText('skipped_human_edit')).toContain('yönetici alanları elle düzeltmişti')
    expect(applyOutcomeText('skipped_not_new')).toContain('artık “Yeni”')
  })

  it('bekleyen, başarısız ve biten iş farklı ton ve metinle görünür', () => {
    expect(jobLine(makeJob())).toMatchObject({ tone: 'info' })
    expect(jobLine(makeJob()).text).toContain('kuyrukta bekliyor')
    expect(jobLine(makeJob({ attempts: 1 })).text).toContain('yeniden denenmek üzere')
    expect(jobLine(makeJob({ status: 'running', attempts: 2 })).text).toContain('2/3 deneme')
    expect(jobLine(makeJob({ status: 'succeeded', outcome: 'decided' })).tone).toBe('success')
    const failed = jobLine(makeJob({ status: 'failed', outcome: 'failed_provider' }))
    expect(failed.tone).toBe('error')
    expect(failed.text).toContain('sağlayıcı yanıt vermedi')
    expect(failed.text).toContain('insan incelemesine alındı')
  })
})

describe('inceleme nedenleri, yargılar, maliyet', () => {
  it('inceleme nedenleri Türkçe; güvenlik terimi ve bilinmeyen kod korunur', () => {
    expect(reasonText('possible_prompt_injection')).toBe('Talimat enjeksiyonu şüphesi')
    expect(reasonText('category_unclear')).toBe('Kategori belirsiz')
    expect(reasonText('safety:kivilcim')).toBe('Güvenlik terimi: kivilcim')
    expect(reasonText('yeni_neden')).toBe('yeni_neden')
  })

  it('cevaplar sözlük adlarıyla; belirsiz ve evet/hayır açık', () => {
    expect(answerText(judgment(), vocab)).toBe('Su/Tesisat')
    expect(answerText(judgment({ question: 'priority', answer: 'high' }), vocab)).toBe('Yüksek')
    expect(answerText(judgment({ answer: 'unclear' }), vocab)).toBe('Belirsiz')
    expect(answerText(judgment({ answer: null }), vocab)).toBe('Belirsiz')
    expect(answerText(judgment({ question: 'missing_contact', answer: true }), vocab)).toBe('Evet')
    expect(answerText(judgment({ question: 'missing_contact', answer: false }), vocab)).toBe('Hayır')
  })

  it('güven değeri türüyle gösterilir; türler birbirine eşdeğer sayılmaz', () => {
    expect(confidenceText(judgment())).toBe('0,93 (modelin kendi yazdığı, kalibre değil)')
    expect(confidenceText(judgment({ confidence: 0.6, confidence_kind: 'jev_confidence' }))).toBe('0,60 (Jev güveni)')
    expect(confidenceText(judgment({ confidence: 0.6, confidence_kind: 'derived_margin' }))).toBe(
      '0,60 (olasılıktan türetilmiş)',
    )
    expect(confidenceText(judgment({ confidence: null }))).toBe('yok')
  })

  it('maliyet: çağrı yoksa söylenir; bilinmeyen ücret sıfır sayılmaz', () => {
    expect(costText(makeDecision())).toBe('Model çağrısı yok.')
    expect(costText(makeDecision({ calls_total: 2, cost_known_usd: '0.0038' }))).toBe(
      '2 çağrı; bilinen ücret 0,0038 USD.',
    )
    const unknown = costText(makeDecision({ calls_total: 3, cost_known_usd: '0', calls_with_unknown_cost: 3 }))
    expect(unknown).toContain('3 çağrının ücreti bilinmiyor')
    expect(unknown).toContain('sıfır sayılmadı')
  })
})

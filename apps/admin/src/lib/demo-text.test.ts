import { describe, expect, it } from 'vitest'

import {
  DEMO_SAMPLES,
  DEMO_STATE_LABELS,
  answerText,
  confidenceText,
  durationText,
  questionLabel,
  tokenText,
  unavailableText,
  validateInput,
} from './demo-text'
import type { DemoJudgment, DemoState } from './demo-types'

const LIMITS = { title_max: 120, description_max: 1000, location_max: 120 }
const judgment = (overrides: Partial<DemoJudgment>): DemoJudgment => ({
  question: 'category',
  answer: 'plumbing',
  confidence: 0.88,
  confidence_kind: 'jev_confidence',
  adopted: true,
  ...overrides,
})

describe('durationText', () => {
  it.each([
    [0, '0 ms'],
    [315, '315 ms'],
    [999, '999 ms'],
    [1000, '1,0 sn'],
    [2266, '2,3 sn'],
    [59_900, '59,9 sn'],
    [64_000, '1 dk 4 sn'],
    [125_000, '2 dk 5 sn'],
  ])('%d ms → %s', (ms, expected) => {
    expect(durationText(ms)).toBe(expected)
  })

  it('bilinmeyen süre sıfır DEĞİL, çizgi', () => {
    expect(durationText(null)).toBe('—')
    expect(durationText(undefined)).toBe('—')
  })
})

describe('güven değerleri', () => {
  it('Jev güveni ile türetilmiş marj AYRI etiketlenir (aynı şey değil)', () => {
    expect(confidenceText(judgment({ confidence: 0.88, confidence_kind: 'jev_confidence' }))).toBe('0,88 (Jev güveni)')
    const derived = confidenceText(judgment({ confidence: 0.6, confidence_kind: 'derived_margin' }))
    expect(derived).toContain('0,60')
    expect(derived).toContain('türetilmiş marj')
    expect(derived).toContain('Jev güveni değil')
  })

  it('güven yoksa uydurulmaz', () => {
    expect(confidenceText(judgment({ confidence: null, confidence_kind: null }))).toBe('—')
  })

  it('bilinmeyen güven türü yalnızca sayıyı gösterir', () => {
    expect(confidenceText(judgment({ confidence: 0.5, confidence_kind: 'baska' }))).toBe('0,50')
  })
})

describe('answerText / questionLabel / tokenText', () => {
  const labels = {
    categories: (code: string) => (code === 'plumbing' ? 'Su/Tesisat' : code),
    priorities: (code: string) => (code === 'high' ? 'Yüksek' : code),
  }

  it('kategori ve öncelik sözlükten, evet/hayır Türkçe', () => {
    expect(answerText(judgment({ answer: 'plumbing' }), labels)).toBe('Su/Tesisat')
    expect(answerText(judgment({ question: 'priority', answer: 'high' }), labels)).toBe('Yüksek')
    expect(answerText(judgment({ question: 'missing_contact', answer: true }), labels)).toBe('evet')
    expect(answerText(judgment({ question: 'missing_contact', answer: false }), labels)).toBe('hayır')
    expect(answerText(judgment({ answer: null }), labels)).toBe('—')
  })

  it('soru etiketleri; bilinmeyen soru kodu kendisi', () => {
    expect(questionLabel('missing_location')).toBe('Konum eksik mi?')
    expect(questionLabel('baska')).toBe('baska')
  })

  it('bildirilmeyen token "bildirilmedi" (sıfır değil)', () => {
    expect(tokenText(null)).toBe('bildirilmedi')
    expect(tokenText(392)).toBe('392')
    expect(tokenText(0)).toBe('0')
  })
})

describe('validateInput', () => {
  const ok = { title: 'Lavabo akıtıyor', description: 'Su koridora yayılıyor, acil.', location: 'B Blok' }

  it('geçerli girdi hata vermez', () => {
    expect(validateInput(ok, LIMITS)).toBeNull()
  })

  it.each([
    [{ title: 'ab' }, 'Başlık en az 3'],
    [{ description: 'kısa' }, 'Açıklama en az 10'],
    [{ location: 'a' }, 'Konum en az 2'],
    [{ title: 'x'.repeat(121) }, 'Başlık en çok 120'],
    [{ description: 'y'.repeat(1001) }, 'Açıklama en çok 1000'],
    [{ location: 'z'.repeat(121) }, 'Konum en çok 120'],
    [{ title: '   ' }, 'Başlık en az 3'],
  ])('geçersiz girdi %j', (patch, message) => {
    expect(validateInput({ ...ok, ...patch }, LIMITS)).toContain(message)
  })

  it('sınır değerleri kabul edilir', () => {
    const edge = { title: 't'.repeat(120), description: 'd'.repeat(1000), location: 'l'.repeat(120) }
    expect(validateInput(edge, LIMITS)).toBeNull()
  })

  it('boşluklar sayılmaz (kırpılmış uzunluk)', () => {
    expect(validateInput({ ...ok, title: `  ${'x'.repeat(120)}  ` }, LIMITS)).toBeNull()
  })
})

describe('hazır örnekler', () => {
  it('hepsi sunucu sınırlarına uyar ve benzersizdir', () => {
    for (const sample of DEMO_SAMPLES) {
      expect(validateInput(sample.input, LIMITS), sample.id).toBeNull()
    }
    expect(new Set(DEMO_SAMPLES.map((s) => s.id)).size).toBe(DEMO_SAMPLES.length)
  })

  it('güvenlik ve enjeksiyon örnekleri bulunur; hiçbirinde "doğru etiket" iddiası yok', () => {
    const labels = DEMO_SAMPLES.map((s) => s.label).join(' ')
    expect(labels).toContain('Gaz kokusu')
    expect(labels).toContain('enjeksiyon')
    for (const sample of DEMO_SAMPLES) {
      expect(JSON.stringify(sample)).not.toMatch(/beklenen|doğru etiket|etiket:/i)
    }
  })
})

describe('durum metinleri', () => {
  it('her durumun Türkçe adı vardır', () => {
    const states: DemoState[] = [
      'pending',
      'running',
      'completed',
      'skipped',
      'failed',
      'uncertain',
      'budget_exhausted',
    ]
    for (const state of states) expect(DEMO_STATE_LABELS[state]).toBeTruthy()
  })

  it('unavailableText: kullanılabilirse null, değilse nedeni', () => {
    expect(unavailableText({ enabled: true, reason: null })).toBeNull()
    expect(unavailableText({ enabled: false, reason: 'budget_exhausted' })).toContain('bütçe doldu')
    expect(unavailableText({ enabled: false, reason: 'not_configured' })).toContain('yapılandırılmadı')
    expect(unavailableText({ enabled: false, reason: 'disabled' })).toContain('kapalı')
    expect(unavailableText({ enabled: false, reason: null })).toContain('kullanılamıyor')
  })
})

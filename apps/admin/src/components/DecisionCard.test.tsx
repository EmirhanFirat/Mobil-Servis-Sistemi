import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DecisionJudgment } from '../lib/types'
import { makeDecision, vocab } from '../test-utils'
import { DecisionCard } from './DecisionCard'

const job = {
  strategy: 'rule_based',
  status: 'succeeded' as const,
  outcome: 'decided' as const,
  attempts: 1,
  max_attempts: 3,
  last_error: null,
  created_at: '2026-10-02T10:00:00Z',
  finished_at: '2026-10-02T10:00:05Z',
}

describe('DecisionCard', () => {
  it('karar bilgisi gelmediyse (yönetici değil) hiçbir şey göstermez', () => {
    const { container } = render(<DecisionCard panel={null} vocab={vocab} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('iş de karar da yoksa bunu söyler', () => {
    render(<DecisionCard panel={{ job: null, decision: null }} vocab={vocab} />)

    expect(screen.getByText('Bu talep için karar işi oluşturulmadı.')).toBeInTheDocument()
  })

  it('bekleyen işi görünür kılar', () => {
    render(
      <DecisionCard
        panel={{ job: { ...job, status: 'pending', outcome: null, attempts: 0 }, decision: null }}
        vocab={vocab}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('kuyrukta bekliyor')
  })

  it('başarısız işi hata olarak gösterir', () => {
    render(
      <DecisionCard
        panel={{ job: { ...job, status: 'failed', outcome: 'failed_provider', attempts: 1 }, decision: null }}
        vocab={vocab}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('sağlayıcı yanıt vermedi')
  })

  it('mock kararı MOCK rozeti ve gerçek ölçüm olmadığı uyarısıyla gösterir', () => {
    render(
      <DecisionCard
        panel={{
          job,
          decision: makeDecision({
            strategy: 'hybrid',
            is_mock: true,
            providers: ['mock-jev', 'mock-llm'],
            model_versions: ['mock-jev-1', 'mock-llm-1'],
            calls_total: 2,
            cost_known_usd: '0',
          }),
        }}
        vocab={vocab}
      />,
    )

    expect(screen.getByText('MOCK — gerçek model değil')).toBeInTheDocument()
    expect(screen.getByText(/gerçek model ölçümü değildir/)).toBeInTheDocument()
    expect(screen.getByText('2 çağrı; bilinen ücret 0 USD.')).toBeInTheDocument()
  })

  it('kural tabanlı karar; önerilen alanlar, inceleme nedenleri ve uygulama sonucu', () => {
    render(
      <DecisionCard
        panel={{
          job,
          decision: makeDecision({
            category: 'electrical',
            priority: 'high',
            missing_info: ['location'],
            review_required: true,
            review_reasons: ['possible_prompt_injection', 'safety:kivilcim'],
            applied_outcome: 'skipped_human_edit',
            applied_at: null,
          }),
        }}
        vocab={vocab}
      />,
    )

    expect(screen.getByText('Kural tabanlı')).toBeInTheDocument()
    expect(screen.getByText('Elektrik')).toBeInTheDocument()
    expect(screen.getByText('Yüksek')).toBeInTheDocument()
    expect(screen.getByText('Konum eksik')).toBeInTheDocument()
    expect(screen.getByText('Talimat enjeksiyonu şüphesi')).toBeInTheDocument()
    expect(screen.getByText('Güvenlik terimi: kivilcim')).toBeInTheDocument()
    expect(screen.getByText(/Uygulanmadı: model çalışırken bir yönetici/)).toBeInTheDocument()
    expect(screen.queryByText(/MOCK/)).not.toBeInTheDocument()
  })

  it('yargı tablosu güven türünü ve karara alınmayan yargıyı gösterir', () => {
    const judgments: DecisionJudgment[] = [
      {
        question: 'category',
        answer: 'plumbing',
        probabilities: { plumbing: 0.9 },
        confidence: 0.8,
        confidence_kind: 'jev_confidence',
        n_options: 6,
        source: 'jev',
        adopted: false,
      },
      {
        question: 'category',
        answer: 'electrical',
        probabilities: null,
        confidence: 0.9,
        confidence_kind: 'self_reported',
        n_options: 6,
        source: 'anthropic',
        adopted: true,
      },
    ]
    render(
      <DecisionCard
        panel={{ job, decision: makeDecision({ strategy: 'hybrid', judgments }) }}
        vocab={vocab}
      />,
    )

    const table = screen.getByRole('table')
    expect(within(table).getByText('0,80 (Jev güveni)')).toBeInTheDocument()
    expect(within(table).getByText('0,90 (modelin kendi yazdığı, kalibre değil)')).toBeInTheDocument()
    expect(within(table).getByText('jev (karara alınmadı)')).toBeInTheDocument()
  })
})

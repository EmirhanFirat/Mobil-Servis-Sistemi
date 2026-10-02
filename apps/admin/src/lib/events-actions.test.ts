import { describe, expect, it } from 'vitest'

import { transitionAction } from './actions'
import { describeEvent, eventNote } from './events'
import { formatDateTime, labelOf, ticketNumber } from './format'
import type { TicketEvent, TicketStatus } from './types'
import { vocab } from '../test-utils'

function event(
  kind: string,
  data: Record<string, unknown> = {},
  actor: string | null = 'Zeynep Yönetici',
): TicketEvent {
  return {
    id: 1,
    kind,
    data,
    created_at: '2026-10-01T10:00:00Z',
    actor: actor ? { id: 'u1', display_name: actor, role: 'admin' } : null,
  }
}

describe('describeEvent', () => {
  it('durum ve ekip değişimleri Türkçe adlarla anlatılır', () => {
    expect(describeEvent(event('status_changed', { from: 'new', to: 'assigned' }), vocab)).toBe(
      'Zeynep Yönetici durumu “Yeni” → “Atandı” yaptı.',
    )
    expect(describeEvent(event('team_changed', { to: 'plumbing' }), vocab)).toBe(
      'Zeynep Yönetici talebi “Su/Tesisat Ekibi” ekibine yönlendirdi.',
    )
    expect(describeEvent(event('team_changed', { from: 'plumbing', to: 'it' }), vocab)).toBe(
      'Zeynep Yönetici talebi “Su/Tesisat Ekibi” ekibinden “BT Ekibi” ekibine taşıdı.',
    )
  })

  it('görevli değişimi adı kullanır; adı olmayan eski kayıtta UUID göstermez', () => {
    expect(describeEvent(event('assignee_changed', { to_name: 'Mehmet' }), vocab)).toBe('Mehmet görevli oldu.')
    expect(describeEvent(event('assignee_changed', { from_name: 'Mehmet' }), vocab)).toContain('görevden ayrıldı')
    expect(describeEvent(event('assignee_changed', { to: 'uuid-1' }), vocab)).toBe('Görevli değişti.')
  })

  it('alan düzeltmeleri: öncelik, kategori, eksik bilgi', () => {
    expect(describeEvent(event('field_changed', { field: 'priority', from: 'normal', to: 'high' }), vocab)).toBe(
      'Zeynep Yönetici öncelik alanını “Normal” → “Yüksek” olarak düzeltti.',
    )
    expect(describeEvent(event('field_changed', { field: 'category', from: 'plumbing' }), vocab)).toBe(
      'Zeynep Yönetici kategori alanını temizledi.',
    )
    expect(describeEvent(event('field_changed', { field: 'missing_info', to: ['location'] }), vocab)).toBe(
      'Zeynep Yönetici eksik bilgiyi düzeltti: Konum eksik.',
    )
  })

  it('karar motoru olayları: kaynak kural tabanlı/mock/gerçek ayrılır, hata görünür', () => {
    const base = { team: 'plumbing', category: 'plumbing', priority: 'high' }
    expect(describeEvent(event('decision_applied', { ...base, strategy: 'rule_based', is_mock: false }, null), vocab)).toBe(
      'Karar motoru (kural tabanlı) talebi “Su/Tesisat Ekibi” ekibinin kuyruğuna yönlendirdi (kategori Su/Tesisat, öncelik Yüksek).',
    )
    expect(describeEvent(event('decision_applied', { ...base, strategy: 'hybrid', is_mock: true }, null), vocab)).toContain(
      'Karar motoru (mock hibrit)',
    )
    expect(describeEvent(event('decision_applied', { strategy: 'llm_only', is_mock: false }, null), vocab)).toBe(
      'Karar motoru (LLM) talebi insan incelemesine yönlendirdi.',
    )
    expect(describeEvent(event('decision_failed', { reason: 'failed_provider' }, null), vocab)).toBe(
      'Karar motoru yanıt veremedi; talep insan incelemesine alındı.',
    )
  })

  it('sistem olayı ve bilinmeyen tür çökmez', () => {
    expect(describeEvent(event('created', {}, null), vocab)).toBe('Sistem talebi açtı.')
    expect(describeEvent(event('gelecekteki_olay', {}, null), vocab)).toBe('Sistem: gelecekteki_olay')
  })
})

describe('eventNote', () => {
  it('yalnızca dolu metin notunu döndürür', () => {
    expect(eventNote(event('status_changed', { note: 'Yinelenen talep' }))).toBe('Yinelenen talep')
    expect(eventNote(event('status_changed', { note: '' }))).toBeNull()
    expect(eventNote(event('status_changed'))).toBeNull()
  })
})

// services/api/app/domain/workflow.py içindeki TRANSITIONS anahtarlarının kopyası. Sunucuya yeni
// bir geçiş eklenirse bu liste ve actions.ts birlikte güncellenmeli; yoksa düğme ham kodla görünür.
const SERVER_TRANSITIONS: [TicketStatus, TicketStatus][] = [
  ['new', 'needs_review'],
  ['new', 'closed'],
  ['needs_review', 'closed'],
  ['assigned', 'in_progress'],
  ['assigned', 'needs_review'],
  ['assigned', 'closed'],
  ['in_progress', 'resolved'],
  ['in_progress', 'assigned'],
  ['in_progress', 'closed'],
  ['resolved', 'closed'],
  ['resolved', 'in_progress'],
]

describe('transitionAction', () => {
  it.each(SERVER_TRANSITIONS)('%s → %s için okunur etiket ve açıklama var', (from, to) => {
    const action = transitionAction(from, to)

    expect(action.label).not.toBe(to)
    expect(action.hint.length).toBeGreaterThan(5)
  })

  it('kapatma geri alınamaz olarak işaretlenir, diğerleri işaretlenmez', () => {
    for (const [from, to] of SERVER_TRANSITIONS) {
      expect(transitionAction(from, to).destructive).toBe(to === 'closed')
    }
  })

  it('aynı hedefin anlamı kaynağa göre değişir', () => {
    expect(transitionAction('assigned', 'in_progress').label).toBe('İşleme al')
    expect(transitionAction('resolved', 'in_progress').label).toBe('Yeniden aç')
    expect(transitionAction('resolved', 'closed').label).toBe('Onaylayıp kapat')
  })
})

describe('format yardımcıları', () => {
  it('talep numarası, etiket ve tarih', () => {
    expect(ticketNumber(7)).toBe('TA-0007')
    expect(labelOf(vocab.statuses, 'in_progress')).toBe('İşlemde')
    expect(labelOf(vocab.statuses, 'bilinmeyen')).toBe('bilinmeyen')
    expect(labelOf(vocab.statuses, null)).toBe('')
    expect(formatDateTime('2026-10-01T10:30:00Z')).toMatch(/^\d{2}\.\d{2}\.2026 \d{2}:\d{2}$/)
    expect(formatDateTime('dün')).toBe('dün')
  })
})

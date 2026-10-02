import { vi } from 'vitest'

import type { ApiClient } from './lib/api'
import type {
  TeamWithMembers,
  TicketDetail,
  Vocabulary,
} from './lib/types'

export const vocab: Vocabulary = {
  roles: [
    { code: 'requester', label: 'Talep sahibi' },
    { code: 'technician', label: 'Teknik görevli' },
    { code: 'admin', label: 'Yönetici' },
  ],
  statuses: [
    { code: 'new', label: 'Yeni' },
    { code: 'needs_review', label: 'İnceleme bekliyor' },
    { code: 'assigned', label: 'Atandı' },
    { code: 'in_progress', label: 'İşlemde' },
    { code: 'resolved', label: 'Çözüldü' },
    { code: 'closed', label: 'Kapatıldı' },
  ],
  priorities: [
    { code: 'low', label: 'Düşük' },
    { code: 'normal', label: 'Normal' },
    { code: 'high', label: 'Yüksek' },
  ],
  categories: [
    { code: 'electrical', label: 'Elektrik' },
    { code: 'plumbing', label: 'Su/Tesisat' },
    { code: 'it_network', label: 'İnternet/BT' },
    { code: 'cleaning', label: 'Temizlik' },
    { code: 'other', label: 'Diğer' },
  ],
  teams: [
    { code: 'electrical', label: 'Elektrik Ekibi' },
    { code: 'plumbing', label: 'Su/Tesisat Ekibi' },
    { code: 'it', label: 'BT Ekibi' },
  ],
  missing_info: [
    { code: 'location', label: 'Konum eksik' },
    { code: 'contact', label: 'İletişim bilgisi eksik' },
  ],
  category_default_team: {
    electrical: 'electrical',
    plumbing: 'plumbing',
    it_network: 'it',
  },
}

export const teams: TeamWithMembers[] = [
  {
    id: 'team-e',
    code: 'electrical',
    name: 'Elektrik Ekibi',
    members: [{ id: 'u-ahmet', display_name: 'Ahmet Elektrik', role: 'technician' }],
  },
  {
    id: 'team-p',
    code: 'plumbing',
    name: 'Su/Tesisat Ekibi',
    members: [{ id: 'u-mehmet', display_name: 'Mehmet Tesisat', role: 'technician' }],
  },
  { id: 'team-i', code: 'it', name: 'BT Ekibi', members: [] },
]

export function makeTicket(overrides: Partial<TicketDetail> = {}): TicketDetail {
  return {
    id: 'ticket-1',
    number: 1,
    title: 'Lavabo akıtıyor',
    description: 'Su koridora yayılıyor.',
    location: 'B Blok',
    status: 'new',
    category: null,
    priority: 'normal',
    team: null,
    assignee: null,
    created_by: { id: 'u-ayse', display_name: 'Ayşe Yılmaz', role: 'requester' },
    missing_info: [],
    review_required: false,
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:00:00Z',
    allowed_transitions: ['needs_review', 'closed'],
    can_assign: true,
    can_edit: true,
    events: [],
    ...overrides,
  }
}

/** Yalnızca gereken uçları vi.fn() olan sahte istemci. */
export function fakeApi(overrides: Record<string, unknown> = {}): ApiClient {
  return {
    assign: vi.fn().mockResolvedValue(makeTicket()),
    patchTicket: vi.fn().mockResolvedValue(makeTicket()),
    transition: vi.fn().mockResolvedValue(makeTicket()),
    ...overrides,
  } as unknown as ApiClient
}

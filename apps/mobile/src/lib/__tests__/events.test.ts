import { describeEvent, eventNote } from '../events';
import type { TicketEvent, Vocabulary } from '../types';

const vocab: Vocabulary = {
  roles: [],
  statuses: [
    { code: 'new', label: 'Yeni' },
    { code: 'assigned', label: 'Atandı' },
    { code: 'in_progress', label: 'İşlemde' },
  ],
  priorities: [
    { code: 'normal', label: 'Normal' },
    { code: 'high', label: 'Yüksek' },
  ],
  categories: [
    { code: 'electrical', label: 'Elektrik' },
    { code: 'plumbing', label: 'Su/Tesisat' },
  ],
  teams: [
    { code: 'electrical', label: 'Elektrik Ekibi' },
    { code: 'plumbing', label: 'Su/Tesisat Ekibi' },
  ],
  missing_info: [
    { code: 'contact', label: 'İletişim bilgisi eksik' },
    { code: 'location', label: 'Konum eksik' },
  ],
  category_default_team: {},
};

function event(kind: string, data: Record<string, unknown> = {}, actorName: string | null = 'Zeynep Yönetici'): TicketEvent {
  return {
    id: 1,
    kind,
    data,
    created_at: '2026-10-01T10:00:00Z',
    actor: actorName ? { id: 'u1', display_name: actorName, role: 'admin' } : null,
  };
}

describe('describeEvent', () => {
  it('talep açılışı', () => {
    expect(describeEvent(event('created', {}, 'Ayşe Yılmaz'), vocab)).toBe('Ayşe Yılmaz talebi açtı.');
  });

  it('durum değişimi Türkçe adlarla', () => {
    expect(describeEvent(event('status_changed', { from: 'assigned', to: 'in_progress' }), vocab)).toBe(
      'Zeynep Yönetici durumu “Atandı” → “İşlemde” yaptı.',
    );
  });

  it('ilk yönlendirme ve ekip değişimi', () => {
    expect(describeEvent(event('team_changed', { to: 'electrical' }), vocab)).toBe(
      'Zeynep Yönetici talebi “Elektrik Ekibi” ekibine yönlendirdi.',
    );
    expect(describeEvent(event('team_changed', { from: 'electrical', to: 'plumbing' }), vocab)).toBe(
      'Zeynep Yönetici talebi “Elektrik Ekibi” ekibinden “Su/Tesisat Ekibi” ekibine taşıdı.',
    );
  });

  it('görevli değişimi: atama, devir ve ayrılma', () => {
    expect(describeEvent(event('assignee_changed', { to_name: 'Ahmet' }), vocab)).toBe('Ahmet görevli oldu.');
    expect(describeEvent(event('assignee_changed', { from_name: 'Ahmet', to_name: 'Elif' }), vocab)).toBe(
      'Görevli Ahmet yerine Elif oldu.',
    );
    expect(describeEvent(event('assignee_changed', { from_name: 'Ahmet' }), vocab)).toBe(
      'Ahmet görevden ayrıldı; talep ekip kuyruğuna döndü.',
    );
  });

  it('eski kayıtlarda ad yoksa genel cümleye düşer (UUID göstermez)', () => {
    const text = describeEvent(event('assignee_changed', { from: 'uuid-1', to: 'uuid-2' }), vocab);

    expect(text).toBe('Görevli değişti.');
    expect(text).not.toContain('uuid');
  });

  it('alan düzeltmeleri: öncelik, kategori, eksik bilgi', () => {
    expect(describeEvent(event('field_changed', { field: 'priority', from: 'normal', to: 'high' }), vocab)).toBe(
      'Zeynep Yönetici öncelik alanını “Normal” → “Yüksek” olarak düzeltti.',
    );
    expect(describeEvent(event('field_changed', { field: 'category', to: 'electrical' }), vocab)).toBe(
      'Zeynep Yönetici kategori alanını “Elektrik” olarak belirledi.',
    );
    expect(describeEvent(event('field_changed', { field: 'category', from: 'electrical' }), vocab)).toBe(
      'Zeynep Yönetici kategori alanını temizledi.',
    );
    expect(describeEvent(event('field_changed', { field: 'missing_info', to: ['contact', 'location'] }), vocab)).toBe(
      'Zeynep Yönetici eksik bilgiyi düzeltti: İletişim bilgisi eksik, Konum eksik.',
    );
    expect(describeEvent(event('field_changed', { field: 'missing_info', to: [] }), vocab)).toBe(
      'Zeynep Yönetici eksik bilgiyi düzeltti: yok.',
    );
  });

  it('sözlükte olmayan kod için kodun kendisini gösterir (boş bırakmaz)', () => {
    expect(describeEvent(event('status_changed', { from: 'new', to: 'yeni_durum' }), vocab)).toContain('“yeni_durum”');
  });

  it('sistem olaylarında oyuncu adı "Sistem" olur; bilinmeyen tür çökmez', () => {
    expect(describeEvent(event('created', {}, null), vocab)).toBe('Sistem talebi açtı.');
    expect(describeEvent(event('gelecekteki_olay', {}, null), vocab)).toBe('Sistem: gelecekteki_olay');
  });
});

describe('eventNote', () => {
  it('notu döndürür, yoksa veya boşsa null', () => {
    expect(eventNote(event('status_changed', { note: 'Kontrol ediyorum.' }))).toBe('Kontrol ediyorum.');
    expect(eventNote(event('status_changed', {}))).toBeNull();
    expect(eventNote(event('status_changed', { note: '' }))).toBeNull();
    expect(eventNote(event('status_changed', { note: 42 }))).toBeNull();
  });
});

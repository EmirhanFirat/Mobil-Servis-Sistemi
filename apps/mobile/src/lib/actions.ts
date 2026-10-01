import type { TicketStatus } from './types';

export interface TransitionAction {
  label: string;
  /** Onay ekranında gösterilen kısa açıklama. */
  hint: string;
  /** Geri alınamaz veya kapatıcı işlemler vurgulanır. */
  destructive: boolean;
}

/**
 * Geçişin kullanıcıya görünen adı. Aynı hedef durumun anlamı kaynağa göre değişir
 * (ör. "İşlemde"ye geçmek: ilk üstlenme mi, yeniden açma mı).
 */
export function transitionAction(from: TicketStatus, to: TicketStatus): TransitionAction {
  if (to === 'in_progress' && from === 'resolved') {
    return {
      label: 'Yeniden aç (sorun sürüyor)',
      hint: 'Talep tekrar işleme alınır ve görevliye döner.',
      destructive: false,
    };
  }
  if (to === 'in_progress') {
    return { label: 'İşleme al', hint: 'İşi üstleniyorsun; talep sana atanır.', destructive: false };
  }
  if (to === 'resolved') {
    return {
      label: 'Çözüldü olarak işaretle',
      hint: 'Talep sahibi çözümü onaylayınca talep kapanır.',
      destructive: false,
    };
  }
  if (to === 'closed' && from === 'resolved') {
    return {
      label: 'Çözümü onayla ve kapat',
      hint: 'Kapatılan talep yeniden açılamaz.',
      destructive: true,
    };
  }
  if (to === 'closed' && (from === 'new' || from === 'needs_review')) {
    return {
      label: 'Talebi iptal et',
      hint: 'Talep kapatılır ve yeniden açılamaz.',
      destructive: true,
    };
  }
  if (to === 'closed') {
    return { label: 'Talebi kapat', hint: 'Kapatılan talep yeniden açılamaz.', destructive: true };
  }
  if (to === 'needs_review') {
    return {
      label: 'İncelemeye gönder',
      hint: 'Yanlış ekip veya eksik bilgi için yönetici incelemesine gider.',
      destructive: false,
    };
  }
  if (to === 'assigned') {
    return {
      label: 'Kuyruğa geri bırak',
      hint: 'İş senden alınır; ekipteki başka bir görevli üstlenebilir.',
      destructive: false,
    };
  }
  return { label: to, hint: '', destructive: false };
}

import type { TicketStatus } from './types'

export interface TransitionAction {
  label: string
  /** Onay adımında gösterilen kısa açıklama. */
  hint: string
  /** Geri alınamaz veya kapatıcı işlemler vurgulanır. */
  destructive: boolean
}

/**
 * Geçişin yöneticiye görünen adı. Aynı hedef durumun anlamı kaynağa göre değişir
 * (ör. "İşlemde"ye geçmek: ilk işleme alma mı, yeniden açma mı).
 */
export function transitionAction(from: TicketStatus, to: TicketStatus): TransitionAction {
  if (to === 'in_progress' && from === 'resolved') {
    return {
      label: 'Yeniden aç',
      hint: 'Talep tekrar işleme alınır ve görevliye döner.',
      destructive: false,
    }
  }
  if (to === 'in_progress') {
    return {
      label: 'İşleme al',
      hint: 'Talep atanmış görevli adına işleme alınır.',
      destructive: false,
    }
  }
  if (to === 'resolved') {
    return {
      label: 'Çözüldü olarak işaretle',
      hint: 'Talep sahibi çözümü onaylayınca talep kapanır.',
      destructive: false,
    }
  }
  if (to === 'closed' && from === 'resolved') {
    return { label: 'Onaylayıp kapat', hint: 'Kapatılan talep yeniden açılamaz.', destructive: true }
  }
  if (to === 'closed') {
    return { label: 'Talebi kapat', hint: 'Kapatılan talep yeniden açılamaz.', destructive: true }
  }
  if (to === 'needs_review') {
    return {
      label: 'İncelemeye al',
      hint: 'Talep yönetici incelemesi bekleyenler arasına alınır; atanmış görevli kaldırılır.',
      destructive: false,
    }
  }
  if (to === 'assigned') {
    return {
      label: 'Kuyruğa geri bırak',
      hint: 'Görevli kaldırılır; ekipteki biri üstlenebilir.',
      destructive: false,
    }
  }
  return { label: to, hint: '', destructive: false }
}

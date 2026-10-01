import { transitionAction } from '../actions';
import type { TicketStatus } from '../types';

// services/api/app/domain/workflow.py içindeki TRANSITIONS tablosunun anahtarlarının kopyası.
// Sunucuya yeni bir geçiş eklenirse bu liste ve actions.ts birlikte güncellenmeli; aksi halde
// aşağıdaki test düğmenin ham durum koduyla görüneceğini yakalar.
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
];

describe('transitionAction', () => {
  it.each(SERVER_TRANSITIONS)('%s → %s için okunur etiket ve açıklama var', (from, to) => {
    const action = transitionAction(from, to);

    expect(action.label).not.toBe(to); // ham kod değil
    expect(action.label.length).toBeGreaterThan(3);
    expect(action.hint.length).toBeGreaterThan(5);
  });

  it('aynı hedefin anlamı kaynağa göre değişir (işlemde: üstlen / yeniden aç)', () => {
    expect(transitionAction('assigned', 'in_progress').label).toBe('İşleme al');
    expect(transitionAction('resolved', 'in_progress').label).toBe('Yeniden aç (sorun sürüyor)');
  });

  it('kapatma işlemleri geri alınamaz olarak işaretlenir ve kaynağa göre adlanır', () => {
    expect(transitionAction('resolved', 'closed')).toMatchObject({ label: 'Çözümü onayla ve kapat', destructive: true });
    expect(transitionAction('new', 'closed')).toMatchObject({ label: 'Talebi iptal et', destructive: true });
    expect(transitionAction('needs_review', 'closed').label).toBe('Talebi iptal et');
    expect(transitionAction('in_progress', 'closed')).toMatchObject({ label: 'Talebi kapat', destructive: true });
  });

  it('kapatma dışındaki işlemler vurgulanmaz', () => {
    for (const [from, to] of SERVER_TRANSITIONS.filter(([, to]) => to !== 'closed')) {
      expect(transitionAction(from, to).destructive).toBe(false);
    }
  });

  it('tanımsız geçişte çökmez, kodu etiket yapar', () => {
    expect(transitionAction('closed', 'new')).toEqual({ label: 'new', hint: '', destructive: false });
  });
});

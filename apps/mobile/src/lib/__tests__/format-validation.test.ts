import { formatDateTime, ticketNumber } from '../format';
import { labelOf } from '../labels';
import { TICKET_LIMITS, validateTicket } from '../validation';

describe('ticketNumber', () => {
  it('4 haneye tamamlar, büyük sayıyı kesmez', () => {
    expect(ticketNumber(1)).toBe('TA-0001');
    expect(ticketNumber(42)).toBe('TA-0042');
    expect(ticketNumber(12345)).toBe('TA-12345');
  });
});

describe('formatDateTime', () => {
  it('geçerli tarihi gün.ay.yıl saat:dakika biçiminde gösterir', () => {
    const text = formatDateTime('2026-10-01T10:30:00Z');

    expect(text).toMatch(/^\d{2}\.\d{2}\.2026 \d{2}:\d{2}$/);
  });

  it('geçersiz tarihi olduğu gibi döndürür (çökmez)', () => {
    expect(formatDateTime('dün')).toBe('dün');
  });
});

describe('labelOf', () => {
  const values = [{ code: 'new', label: 'Yeni' }];

  it('adı bulur, bulamazsa kodu, boşsa boş metni döndürür', () => {
    expect(labelOf(values, 'new')).toBe('Yeni');
    expect(labelOf(values, 'bilinmeyen')).toBe('bilinmeyen');
    expect(labelOf(values, null)).toBe('');
    expect(labelOf(values, undefined)).toBe('');
  });
});

describe('validateTicket', () => {
  it('boş ve yalnızca boşluk içeren alanları reddeder', () => {
    expect(validateTicket({ title: '', description: '   ', location: '\n' })).toEqual({
      title: 'Başlık boş olamaz.',
      description: 'Ne olduğunu kısaca anlat.',
      location: 'Bina ve konumu yaz (ör. B Blok, 2. kat).',
    });
  });

  it('dolu alanlarda hata yoktur', () => {
    expect(validateTicket({ title: 'Musluk', description: 'Akıtıyor', location: 'A Blok' })).toEqual({});
  });

  it('sınırlar sunucuyla aynıdır', () => {
    expect(TICKET_LIMITS).toEqual({ title: 200, description: 4000, location: 200 });
  });
});

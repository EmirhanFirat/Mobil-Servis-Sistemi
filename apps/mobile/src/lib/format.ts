/** TA-0042 biçiminde okunur talep numarası. */
export function ticketNumber(number: number): string {
  return `TA-${String(number).padStart(4, '0')}`;
}

/** "03.10.2026 14:30" biçimi (Türkiye yerel ayarı; desteklenmiyorsa ISO'dan türetilir). */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat('tr-TR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
      .format(date)
      .replace(',', '');
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}

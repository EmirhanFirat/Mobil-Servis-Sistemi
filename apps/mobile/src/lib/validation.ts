/** Alan sınırları sunucuyla aynıdır (services/api/app/schemas.py). */
export const TICKET_LIMITS = { title: 200, description: 4000, location: 200 } as const;

export type TicketField = keyof typeof TICKET_LIMITS;
export type TicketErrors = Partial<Record<TicketField, string>>;

/** İstemci tarafı kontrol yalnızca kullanım kolaylığıdır; asıl doğrulama sunucudadır. */
export function validateTicket(values: Record<TicketField, string>): TicketErrors {
  const errors: TicketErrors = {};
  if (!values.title.trim()) errors.title = 'Başlık boş olamaz.';
  if (!values.description.trim()) errors.description = 'Ne olduğunu kısaca anlat.';
  if (!values.location.trim()) errors.location = 'Bina ve konumu yaz (ör. B Blok, 2. kat).';
  return errors;
}

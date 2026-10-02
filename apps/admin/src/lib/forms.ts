import type {
  Category,
  Priority,
  TeamWithMembers,
  TicketPatchBody,
  TicketSummary,
  Vocabulary,
} from './types'

/**
 * Atama formunda ön seçili ekip: talebin mevcut ekibi; yoksa kategorisinin varsayılan ekibi
 * (sözlükteki tek doğruluk kaynağı); o da yoksa boş. Ekip ve kategori birbirinden bağımsız
 * tahmin edilmez: ekip kategoriden türetilir, yönetici istediğini değiştirebilir.
 */
export function suggestedTeamId(
  ticket: Pick<TicketSummary, 'team' | 'category'>,
  teams: TeamWithMembers[],
  vocab: Vocabulary,
): string {
  if (ticket.team) return ticket.team.id
  if (!ticket.category) return ''
  const code = vocab.category_default_team[ticket.category]
  return teams.find((team) => team.code === code)?.id ?? ''
}

export function sameSet(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false
  const left = [...a].sort()
  const right = [...b].sort()
  return left.every((value, index) => value === right[index])
}

export interface CorrectionForm {
  priority: Priority
  /** Boş metin: kategori belirtilmemiş. */
  category: Category | ''
  missing: string[]
  note: string
}

/**
 * Yalnızca değişen alanları içeren düzeltme gövdesi; hiçbir şey değişmediyse null.
 * Sunucu aynı değeri tekrar göndermeyi zaten olay üretmeden yok sayar, ama gereksiz
 * istek ve "kaydedildi" gürültüsü olmasın diye istemci de eler.
 */
export function buildPatch(
  ticket: Pick<TicketSummary, 'priority' | 'category' | 'missing_info'>,
  form: CorrectionForm,
): TicketPatchBody | null {
  const patch: TicketPatchBody = {}
  if (form.priority !== ticket.priority) patch.priority = form.priority
  if ((form.category || null) !== ticket.category) patch.category = form.category || null
  if (!sameSet(form.missing, ticket.missing_info)) patch.missing_info = form.missing
  if (Object.keys(patch).length === 0) return null
  const note = form.note.trim()
  if (note) patch.note = note
  return patch
}

const USERNAME = /^[A-Za-z0-9._-]{3,50}$/

export interface UserForm {
  username: string
  display_name: string
  password: string
}

/** İstemci tarafı kontrol yalnızca kullanım kolaylığıdır; asıl doğrulama sunucudadır. */
export function validateUserForm(form: UserForm): Partial<Record<keyof UserForm, string>> {
  const errors: Partial<Record<keyof UserForm, string>> = {}
  if (!USERNAME.test(form.username.trim())) {
    errors.username = '3–50 karakter; harf, rakam, nokta, tire veya alt çizgi.'
  }
  if (!form.display_name.trim()) errors.display_name = 'Ad boş olamaz.'
  if (form.password.length < 8) errors.password = 'Parola en az 8 karakter olmalı.'
  return errors
}

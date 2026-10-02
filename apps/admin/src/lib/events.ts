import { labelOf } from './format'
import type { TicketEvent, Vocabulary } from './types'

const FIELD_NAMES: Record<string, string> = {
  priority: 'öncelik',
  category: 'kategori',
  missing_info: 'eksik bilgi',
}

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null

function missingInfoText(value: unknown, vocab: Vocabulary): string {
  if (!Array.isArray(value) || value.length === 0) return 'yok'
  return value.map((code) => labelOf(vocab.missing_info, String(code))).join(', ')
}

/** Olay geçmişindeki bir kaydı Türkçe bir cümleye çevirir (not ayrıca gösterilir). */
export function describeEvent(event: TicketEvent, vocab: Vocabulary): string {
  const who = event.actor?.display_name ?? 'Sistem'
  const data = event.data

  switch (event.kind) {
    case 'created':
      return `${who} talebi açtı.`

    case 'status_changed':
      return `${who} durumu “${labelOf(vocab.statuses, text(data.from))}” → “${labelOf(vocab.statuses, text(data.to))}” yaptı.`

    case 'team_changed': {
      const to = labelOf(vocab.teams, text(data.to))
      const from = text(data.from)
      return from
        ? `${who} talebi “${labelOf(vocab.teams, from)}” ekibinden “${to}” ekibine taşıdı.`
        : `${who} talebi “${to}” ekibine yönlendirdi.`
    }

    case 'assignee_changed': {
      const from = text(data.from_name)
      const to = text(data.to_name)
      if (from && to) return `Görevli ${from} yerine ${to} oldu.`
      if (to) return `${to} görevli oldu.`
      if (from) return `${from} görevden ayrıldı; talep ekip kuyruğuna döndü.`
      return 'Görevli değişti.'
    }

    case 'field_changed': {
      const field = text(data.field) ?? ''
      const name = FIELD_NAMES[field] ?? field
      if (field === 'missing_info') {
        return `${who} eksik bilgiyi düzeltti: ${missingInfoText(data.to, vocab)}.`
      }
      const list = field === 'priority' ? vocab.priorities : vocab.categories
      const from = text(data.from)
      const to = text(data.to)
      if (from && to) {
        return `${who} ${name} alanını “${labelOf(list, from)}” → “${labelOf(list, to)}” olarak düzeltti.`
      }
      if (to) return `${who} ${name} alanını “${labelOf(list, to)}” olarak belirledi.`
      return `${who} ${name} alanını temizledi.`
    }

    case 'decision_applied': {
      const source = decisionSourceName(data)
      const summary = decisionSummary(data, vocab)
      const team = text(data.team)
      return team
        ? `Karar motoru (${source}) talebi “${labelOf(vocab.teams, team)}” ekibinin kuyruğuna yönlendirdi${summary}.`
        : `Karar motoru (${source}) talebi insan incelemesine yönlendirdi${summary}.`
    }

    case 'decision_failed':
      return 'Karar motoru yanıt veremedi; talep insan incelemesine alındı.'

    default:
      return `${who}: ${event.kind}`
  }
}

const STRATEGY_NAMES: Record<string, string> = {
  llm_only: 'LLM',
  jev_only: 'Jev',
  hybrid: 'hibrit',
}

/** Olayın karar kaynağı: kural tabanlı, mock (sahte) ya da gerçek strateji adı. */
function decisionSourceName(data: Record<string, unknown>): string {
  const strategy = text(data.strategy) ?? 'bilinmeyen'
  if (strategy === 'rule_based') return 'kural tabanlı'
  const name = STRATEGY_NAMES[strategy] ?? strategy
  return data.is_mock === true ? `mock ${name}` : name
}

function decisionSummary(data: Record<string, unknown>, vocab: Vocabulary): string {
  const parts: string[] = []
  const category = text(data.category)
  const priority = text(data.priority)
  if (category) parts.push(`kategori ${labelOf(vocab.categories, category)}`)
  if (priority) parts.push(`öncelik ${labelOf(vocab.priorities, priority)}`)
  return parts.length > 0 ? ` (${parts.join(', ')})` : ''
}

/** Olaya iliştirilmiş serbest metin notu (varsa). */
export function eventNote(event: TicketEvent): string | null {
  return text(event.data.note)
}

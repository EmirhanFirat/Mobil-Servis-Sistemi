import { describe, expect, it } from 'vitest'

import { buildPatch, sameSet, suggestedTeamId, validateUserForm } from './forms'
import { teams, vocab } from '../test-utils'

describe('suggestedTeamId', () => {
  it('mevcut ekip varsa onu korur (kategoriye bakmaz)', () => {
    const ticket = { team: { id: 'team-i', code: 'it', name: 'BT Ekibi' }, category: 'plumbing' as const }

    expect(suggestedTeamId(ticket, teams, vocab)).toBe('team-i')
  })

  it('ekip yoksa kategorinin varsayılan ekibini önerir', () => {
    expect(suggestedTeamId({ team: null, category: 'plumbing' }, teams, vocab)).toBe('team-p')
    expect(suggestedTeamId({ team: null, category: 'it_network' }, teams, vocab)).toBe('team-i')
  })

  it('kategori yoksa veya eşleşen ekip bulunmazsa boş döner', () => {
    expect(suggestedTeamId({ team: null, category: null }, teams, vocab)).toBe('')
    // "diğer" için sözlükte varsayılan ekip tanımlı değil (bu test sözlüğünde)
    expect(suggestedTeamId({ team: null, category: 'other' }, teams, vocab)).toBe('')
  })
})

describe('sameSet', () => {
  it('sıradan bağımsız küme eşitliği', () => {
    expect(sameSet(['a', 'b'], ['b', 'a'])).toBe(true)
    expect(sameSet([], [])).toBe(true)
    expect(sameSet(['a'], ['a', 'b'])).toBe(false)
    expect(sameSet(['a', 'b'], ['a', 'c'])).toBe(false)
  })
})

describe('buildPatch', () => {
  const ticket = { priority: 'normal' as const, category: null, missing_info: ['location'] }
  const same = { priority: 'normal' as const, category: '' as const, missing: ['location'], note: '' }

  it('hiçbir şey değişmediyse null döner (not tek başına değişiklik sayılmaz)', () => {
    expect(buildPatch(ticket, same)).toBeNull()
    expect(buildPatch(ticket, { ...same, note: 'sadece not' })).toBeNull()
  })

  it('yalnızca değişen alanları gönderir', () => {
    expect(buildPatch(ticket, { ...same, priority: 'high' })).toEqual({ priority: 'high' })
    expect(buildPatch(ticket, { ...same, category: 'plumbing' })).toEqual({ category: 'plumbing' })
    expect(buildPatch(ticket, { ...same, missing: ['location', 'contact'] })).toEqual({
      missing_info: ['location', 'contact'],
    })
  })

  it('kategoriyi temizlemek null gönderir', () => {
    const withCategory = { ...ticket, category: 'plumbing' as const }

    expect(buildPatch(withCategory, { ...same, category: '' })).toEqual({ category: null })
  })

  it('eksik bilgi sırası değişse de değişiklik sayılmaz', () => {
    const two = { ...ticket, missing_info: ['location', 'contact'] }

    expect(buildPatch(two, { ...same, missing: ['contact', 'location'] })).toBeNull()
  })

  it('değişiklik varsa kırpılmış notu ekler', () => {
    expect(buildPatch(ticket, { ...same, priority: 'low', note: '  Acil değil  ' })).toEqual({
      priority: 'low',
      note: 'Acil değil',
    })
  })
})

describe('validateUserForm', () => {
  it('geçerli formda hata yoktur (büyük harf kullanıcı adı kabul edilir)', () => {
    expect(
      validateUserForm({ username: 'Yeni.Usta', display_name: 'Yeni Usta', password: 'gecici-parola' }),
    ).toEqual({})
  })

  it('kurallara uymayan alanları işaretler', () => {
    const errors = validateUserForm({ username: 'a b', display_name: '  ', password: 'kisa' })

    expect(Object.keys(errors).sort()).toEqual(['display_name', 'password', 'username'])
  })
})

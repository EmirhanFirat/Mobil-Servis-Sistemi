import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RUN_ID, makeDetail, makeList, makeRun, makeSample } from '../experiment-fixtures'
import type { ExperimentSource } from '../lib/api'
import { runDate } from '../lib/experiments'
import { createStaticSource } from '../lib/static-experiments'
import { vocab } from '../test-utils'
import AboutPage from './AboutPage'

/** Statik kaynak: s003 tartışmasız, s023 tartışmalı (kayıtlı örnekte gösterilmez). */
function recordedSource(): ExperimentSource {
  const s003 = makeSample()
  s003.sample = {
    ...s003.sample,
    id: 's003',
    title: 'lavabo akitiyor',
    description: 'lavabodan surekli su akiyor, yer su oldu yardim edin',
    location: 'C blok 1. kat tuvaletler',
    disputed: null,
  }
  return createStaticSource({
    list: makeList(),
    details: { [RUN_ID]: makeDetail() },
    samples: { [RUN_ID]: { s003, s023: makeSample() } },
  })
}

describe('AboutPage', () => {
  it('projeyi, üç adımı ve motorların nasıl ayrıldığını anlatır; ölçüm sonuçlarına bağlantı verir', () => {
    render(<AboutPage vocab={vocab} experiments={null} />)

    const intro = screen.getByRole('region', { name: 'TalepAkış hakkında' })
    expect(intro).toHaveTextContent('Türkçe servis taleplerini kategorize eden')
    expect(within(intro).getAllByRole('listitem')).toHaveLength(3)
    expect(within(intro).getByRole('link', { name: /Ölçüm sonuçları/ })).toHaveAttribute('href', '#/sonuclar')
    const engines = screen.getByRole('region', { name: 'Portaldaki talepleri kim değerlendiriyor?' })
    expect(engines).toHaveTextContent('kural tabanlı')
    expect(engines).toHaveTextContent('model çıktısı hiçbir yetki vermez')
  })

  it('kayıtlı örnek kartı "Kayıtlı örnek · tarih" etiketiyle gelir; tartışmalı örnek seçilmez', async () => {
    render(<AboutPage vocab={vocab} experiments={recordedSource()} />)

    const card = await screen.findByRole('region', { name: 'Kayıtlı örnek' })
    expect(within(card).getByText(`Kayıtlı örnek · ${runDate(makeRun())}`)).toHaveClass('badge-recorded')
    expect(card).toHaveTextContent('lavabo akitiyor')
    expect(card).not.toHaveTextContent('Asansör')
    expect(card).toHaveTextContent('Gerçek Jev (jev-1.13.0)')
    expect(card).toHaveTextContent('320 ms')
    expect(card).toHaveTextContent('0,000038682 USD')
    expect(card).toHaveTextContent('canlı istek değil')
    expect(within(card).getByRole('link', { name: /Tüm ölçüm sonuçları/ })).toHaveAttribute('href', '#/sonuclar')
  })

  it('kayıtlı karar yoksa uydurma kart yerine "Ölçüm sonuçları" düğmesi', () => {
    render(<AboutPage vocab={vocab} experiments={null} />)

    expect(screen.queryByRole('region', { name: 'Kayıtlı örnek' })).toBeNull()
    const link = screen.getByRole('link', { name: /Ölçüm sonuçlarını incele/ })
    expect(link).toHaveClass('btn-primary')
  })
})

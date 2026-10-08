import { describe, expect, it, vi } from 'vitest'

import { RUN_ID, makeDetail, makeList, makeSample } from '../experiment-fixtures'
import { vocab } from '../test-utils'
import { ApiError } from './api'
import { createStaticSource, loadStaticBundle, type StaticExperiments } from './static-experiments'

const DATA: StaticExperiments = {
  list: makeList(),
  details: { [RUN_ID]: makeDetail() },
  samples: { [RUN_ID]: { s023: makeSample() } },
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('createStaticSource', () => {
  it('liste, ayrıntı ve örneği statik veriden verir', async () => {
    const source = createStaticSource(DATA)

    expect(await source.listExperiments()).toEqual(DATA.list)
    expect((await source.getExperiment(RUN_ID)).run.id).toBe(RUN_ID)
    expect((await source.getExperimentSample(RUN_ID, 's023')).sample.id).toBe('s023')
  })

  it('olmayan deney ve örnek 404 ApiError (uydurma veri yok)', async () => {
    const source = createStaticSource(DATA)

    await expect(source.getExperiment('yok')).rejects.toMatchObject({ status: 404 })
    await expect(source.getExperiment('yok')).rejects.toBeInstanceOf(ApiError)
    await expect(source.getExperimentSample(RUN_ID, 'yok')).rejects.toMatchObject({ status: 404 })
    await expect(source.getExperimentSample('yok', 's023')).rejects.toMatchObject({ status: 404 })
  })
})

describe('loadStaticBundle', () => {
  it('iki statik dosyayı temel adresten okur; yalnızca GET, API adresi yok', async () => {
    const fetchImpl = vi.fn(async (url: string) =>
      jsonResponse(String(url).endsWith('experiments.json') ? DATA : vocab),
    ) as unknown as typeof fetch

    const bundle = await loadStaticBundle('/', fetchImpl)

    const urls = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0] as string)
    expect(urls.sort()).toEqual(['/demo-data/experiments.json', '/demo-data/vocabulary.json'])
    expect(bundle.vocabulary.categories.length).toBeGreaterThan(0)
    expect((await bundle.source.listExperiments()).runs).toHaveLength(1)
  })

  it('alt dizin temel adresinde eksik eğik çizgiyi tamamlar', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({})) as unknown as typeof fetch

    await loadStaticBundle('/talepakis', fetchImpl)

    const urls = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0] as string)
    expect(urls).toContain('/talepakis/demo-data/experiments.json')
  })

  it('dosya okunamazsa açık hata verir', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, 404)) as unknown as typeof fetch

    await expect(loadStaticBundle('/', fetchImpl)).rejects.toThrow(/okunamadı \(404\)/)
  })
})

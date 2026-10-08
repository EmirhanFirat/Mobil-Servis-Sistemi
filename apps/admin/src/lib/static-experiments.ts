import { ApiError, type ExperimentSource } from './api'
import type { ExperimentDetail, ExperimentList, ExperimentSample } from './experiment-types'
import type { Vocabulary } from './types'

/**
 * Önceden hazırlanmış (statik) deney sonuçları: `python -m app.manage export-demo-data` ile
 * `public/demo-data/` altına yazılır. API uyanmadan açılabilir; yalnızca OKUNUR, hiçbir model
 * çağrısı yapılmaz. Şema, yönetici panelinin API'den aldığıyla aynıdır.
 */
export interface StaticExperiments {
  list: ExperimentList
  details: Record<string, ExperimentDetail>
  samples: Record<string, Record<string, ExperimentSample>>
}

export function createStaticSource(data: StaticExperiments): ExperimentSource {
  return {
    listExperiments: async () => data.list,
    getExperiment: async (runId: string) => {
      const detail = data.details[runId]
      if (!detail) throw new ApiError(404, 'not_found', 'Deney bulunamadı.')
      return detail
    },
    getExperimentSample: async (runId: string, sampleId: string) => {
      const sample = data.samples[runId]?.[sampleId]
      if (!sample) throw new ApiError(404, 'not_found', 'Örnek bulunamadı.')
      return sample
    },
  }
}

export interface StaticBundle {
  source: ExperimentSource
  vocabulary: Vocabulary
}

async function fetchJson<T>(url: string, fetchImpl: typeof fetch): Promise<T> {
  const response = await fetchImpl(url, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Statik sonuç dosyası okunamadı (${response.status}).`)
  return (await response.json()) as T
}

/** `baseUrl` genellikle `import.meta.env.BASE_URL`dir (sonu `/` ile biter). */
export async function loadStaticBundle(
  baseUrl: string,
  fetchImpl: typeof fetch = (...args) => fetch(...args),
): Promise<StaticBundle> {
  const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  const [experiments, vocabulary] = await Promise.all([
    fetchJson<StaticExperiments>(`${base}demo-data/experiments.json`, fetchImpl),
    fetchJson<Vocabulary>(`${base}demo-data/vocabulary.json`, fetchImpl),
  ])
  return { source: createStaticSource(experiments), vocabulary }
}

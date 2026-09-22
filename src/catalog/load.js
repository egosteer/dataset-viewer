import { publicEpisode, createCatalog, readJsonLines } from './catalog.js'

export async function loadCatalog(indexUrl, fallbackUrl, fetcher = fetch, timeoutMs = 15000) {
  async function read(url, compressed) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), compressed ? 60000 : timeoutMs)
    try {
      const response = await fetcher(url, { credentials: 'omit', signal: controller.signal })
      if (!response.ok) throw new Error(`Index unavailable (HTTP ${response.status})`)
      if (!response.body) throw new Error('Empty index response')
      const input = compressed
        ? new Response(response.body.pipeThrough(new DecompressionStream('gzip')))
        : response
      const records = []
      await readJsonLines(input, row => records.push(publicEpisode(row)))
      if (!records.length) throw new Error('Empty index')
      return createCatalog(records)
    } finally { clearTimeout(timer) }
  }
  try { return await read(indexUrl, false) }
  catch {
    try { return await read(fallbackUrl, true) }
    catch { throw new Error('Neither the online catalog nor the bundled catalog could be loaded. Please retry.') }
  }
}

import { publicEpisode, createCatalog, readJsonLines } from './catalog.js'

let loading
function load(indexUrl) {
  if (!loading) loading = (async () => {
    let response
    try { response = await fetch(indexUrl, { credentials: 'omit' }) }
    catch { throw new Error('Cannot load the public dataset index. Check the COS URL and its CORS settings.') }
    if (!response.ok) throw new Error(`Public dataset index is unavailable (HTTP ${response.status}).`)
    const rows = []
    await readJsonLines(response, row => rows.push(publicEpisode(row)))
    if (!rows.length) throw new Error('The public dataset index is empty.')
    return createCatalog(rows)
  })().catch(error => { loading = null; throw error })
  return loading
}
self.onmessage = async ({ data }) => {
  const { id, request, indexUrl } = data
  try {
    const query = await load(indexUrl)
    self.postMessage({ id, result: query(request) })
  } catch (error) { self.postMessage({ id, error: error.message }) }
}

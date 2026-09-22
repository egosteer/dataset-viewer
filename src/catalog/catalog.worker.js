import { loadCatalog } from './load.js'

let loading
function load(indexUrl, fallbackUrl) {
  if (!loading) loading = loadCatalog(indexUrl, fallbackUrl)
    .catch(error => { loading = null; throw error })
  return loading
}
self.onmessage = async ({ data }) => {
  const { id, request, indexUrl, fallbackUrl } = data
  try {
    const query = await load(indexUrl, fallbackUrl)
    self.postMessage({ id, result: query(request) })
  } catch (error) { self.postMessage({ id, error: error.message }) }
}

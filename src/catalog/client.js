const indexUrl = import.meta.env.VITE_DATASET_INDEX_URL ||
  'https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/index.jsonl'
const localDebug = import.meta.env.DEV && import.meta.env.VITE_DATA_SOURCE === 'local'
let worker, nextId = 0
const pending = new Map()

function getWorker() {
  if (!worker) {
    worker = new Worker(new URL('./catalog.worker.js', import.meta.url), { type: 'module' })
    worker.onmessage = ({ data }) => {
      const request = pending.get(data.id)
      if (!request) return
      data.error ? request.reject(new Error(data.error)) : request.resolve(data.result)
    }
    worker.onerror = () => {
      for (const request of [...pending.values()]) request.reject(new Error('The dataset worker could not load. Please retry.'))
      worker.terminate()
      worker = null
    }
  }
  return worker
}

export async function datasetGet(request, signal) {
  if (localDebug) {
    const response = await fetch(request, { signal })
    if (!response.ok) throw new Error((await response.json()).error || 'Unable to load data')
    return response.json()
  }
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
  return new Promise((resolve, reject) => {
    const id = ++nextId
    const cleanup = () => { pending.delete(id); signal?.removeEventListener('abort', abort) }
    const abort = () => { cleanup(); reject(new DOMException('Aborted', 'AbortError')) }
    pending.set(id, {
      resolve: result => { cleanup(); resolve(result) },
      reject: error => { cleanup(); reject(error) },
    })
    signal?.addEventListener('abort', abort, { once: true })
    try { getWorker().postMessage({ id, request, indexUrl }) }
    catch (error) { cleanup(); reject(error) }
  })
}

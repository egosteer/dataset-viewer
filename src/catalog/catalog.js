// Shared pure query logic; the public catalog lives in a browser worker.
export function publicEpisode(r) {
  if (!Number.isInteger(r.episode_index) || typeof r.task_name !== 'string' ||
      !['train', 'val'].includes(r.split)) throw new Error('Invalid public index record')
  const media = field => Object.fromEntries(['head', 'chest'].map(camera => {
    const value = r[field]?.[camera]
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Public media requires HTTPS URLs')
    return [camera, url.href]
  }))
  const language = lang => {
    const values = r.annotations?.[lang] || []
    if (!Array.isArray(values) || !values.every(v => typeof v === 'string')) throw new Error('Invalid annotations')
    return values
  }
  return {
    episode_index: r.episode_index, task_name: r.task_name,
    task_name_original: r.task_name_original, split: r.split,
    num_frames: r.num_frames, fps: r.fps, duration_seconds: r.duration_seconds,
    videos: media('videos'), thumbnails: media('thumbnails'),
    annotations: { en: language('en'), zh: language('zh') },
  }
}

export function createCatalog(records) {
  const rows = [...records].sort((a, b) => a.episode_index - b.episode_index)
  const byId = new Map(), counts = new Map()
  for (const r of rows) {
    if (byId.has(r.episode_index)) throw new Error('Duplicate episode in public index')
    byId.set(r.episode_index, r)
    counts.set(r.task_name, (counts.get(r.task_name) || 0) + 1)
  }
  const tasks = [...counts].sort(([a], [b]) => a.localeCompare(b)).map(([task_name, count]) =>
    ({ task_name, episode_count: count, ready_count: count }))
  return function query(request) {
    const url = new URL(request, 'https://catalog.local')
    if (url.pathname === '/api/catalog') return {
      tasks, progress: { status: 'published', total_episodes: rows.length, ready_episodes: rows.length, preview: false },
    }
    if (url.pathname === '/api/episodes') {
      const task = url.searchParams.get('task'), split = url.searchParams.get('split')
      const q = (url.searchParams.get('q') || '').trim().toLowerCase()
      const filtered = rows.filter(r => (!task || r.task_name === task) && (!split || r.split === split) &&
        (!q || `${String(r.episode_index).padStart(6, '0')} ${r.task_name} ${r.annotations.en.join(' ')} ${r.annotations.zh.join(' ')}`.toLowerCase().includes(q)))
      const page = Math.max(1, Number.parseInt(url.searchParams.get('page')) || 1)
      return { total: filtered.length, page, page_size: 12,
        items: filtered.slice((page - 1) * 12, page * 12).map(({ annotations, videos, ...r }) =>
          ({ ...r, instruction: annotations.en[0] || '' })) }
    }
    const match = url.pathname.match(/^\/api\/episodes\/(\d+)$/)
    const record = match && byId.get(Number(match[1]))
    if (!record) throw new Error('Episode not found')
    return record
  }
}

export async function readJsonLines(response, consume) {
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let boundary
      while ((boundary = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, boundary).trim()
        buffer = buffer.slice(boundary + 1)
        if (line) consume(JSON.parse(line))
      }
      if (done) break
    }
    if (buffer.trim()) consume(JSON.parse(buffer))
  } finally { reader.releaseLock() }
}

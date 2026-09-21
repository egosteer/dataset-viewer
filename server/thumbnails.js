import { mkdir, stat } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const run = promisify(execFile)
const cacheDir = process.env.THUMBNAIL_DIR || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../data/thumbnails')
const jobs = new Map()
let active = 0
const queue = []
async function acquire() {
  if (active < 2) { active++; return }
  await new Promise(resolve => queue.push(resolve))
}
function release() { const next = queue.shift(); if (next) next(); else active-- }
export async function thumbnail(source) {
  const info = await stat(source)
  const key = createHash('sha256').update(`${source}:${info.size}:${info.mtimeMs}`).digest('hex')
  const target = path.join(cacheDir, `${key}.jpg`)
  try { await stat(target); return target } catch {}
  if (jobs.has(key)) return jobs.get(key)
  const job = (async () => {
    await acquire()
    try {
      await mkdir(cacheDir, { recursive: true })
      // Decode only the first frame. At most two FFmpeg jobs run concurrently.
      await run(process.env.FFMPEG_PATH || 'ffmpeg', ['-v', 'error', '-threads', '1', '-i', source, '-frames:v', '1', '-vf', 'scale=640:480', '-threads', '1', '-q:v', '4', '-f', 'image2', '-y', target], { timeout: 20000 })
      return target
    } finally { release(); jobs.delete(key) }
  })()
  jobs.set(key, job)
  return job
}

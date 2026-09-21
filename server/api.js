import { thumbnail } from './thumbnails.js'
import express from 'express'
import { readFile, stat } from 'node:fs/promises'
import { createReadStream } from 'node:fs'
import { createInterface } from 'node:readline'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const defaultDataDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../data/preview')
export function createDatasetApp(dataDir = process.env.DATASET_DIR || defaultDataDir) {
  const app = express()
  let cache, signature, pending
  const publicRecord = r => ({ episode_index: r.episode_index, task_name: r.task_name, split: r.split, num_frames: r.num_frames, fps: r.fps, duration_seconds: r.duration_seconds, thumbnails: {head: `/api/thumbnails/${r.episode_index}/head`, chest: `/api/thumbnails/${r.episode_index}/chest`}, annotations: { en: r.annotations?.en || [], zh: r.annotations?.zh || [] }, videos: Object.fromEntries(['head','chest'].map(c => [c, `/dataset/${r.videos[c]}`])) })
  async function catalog() {
    const files = ['index.ready.jsonl', 'tasks.json', 'progress.json']
    const stamps = await Promise.all(files.map(f => stat(path.join(dataDir,f))))
    const next = stamps.map(s => `${s.mtimeMs}:${s.size}`).join('|')
    if (cache && signature === next) return cache
    if (pending) return pending
    pending = (async () => {
      const rows = []
      const lines = createInterface({ input: createReadStream(path.join(dataDir,files[0])), crlfDelay: Infinity })
      for await (const line of lines) {
        if (!line.trim()) continue
        const r = JSON.parse(line)
        if (!Number.isInteger(r.episode_index) || !['head','chest'].every(c => /^assets\/episodes\/\d{6,}\/(head|chest)\.mp4$/.test(r.videos?.[c] || ''))) throw new Error('Invalid ready record')
        rows.push(publicRecord(r))
      }
      rows.sort((a,b) => a.episode_index-b.episode_index)
      const tasks = JSON.parse(await readFile(path.join(dataDir,files[1]),'utf8'))
      const source = JSON.parse(await readFile(path.join(dataDir,files[2]),'utf8'))
      const counts = new Map()
      for (const r of rows) counts.set(r.task_name,(counts.get(r.task_name)||0)+1)
      cache = { rows, tasks: tasks.map(t => ({ task_name:t.task_name, episode_count:t.episode_count, ready_count:counts.get(t.task_name)||0 })), progress: { status: source.status, total_episodes:source.total_episodes, ready_episodes:rows.length, preview:source.preview===true, updated_at:source.updated_at } }
      signature = next
      return cache
    })().finally(() => { pending = null })
    return pending
  }
  app.get('/api/catalog', async (req,res,next) => {
    try { const {tasks,progress} = await catalog(); res.json({tasks,progress}) } catch(e) {next(e)}
  })
  app.get('/api/episodes', async (req,res,next) => {
    try {
      const {rows} = await catalog()
      const task = String(req.query.task || ''), split = String(req.query.split || ''), q = String(req.query.q || '').toLowerCase().trim()
      const filtered = rows.filter(r => (!task || r.task_name===task) && (!split || r.split===split) && (!q || `${String(r.episode_index).padStart(6,'0')} ${r.task_name} ${r.annotations.en.join(' ')} ${r.annotations.zh.join(' ')}`.toLowerCase().includes(q)))
      const page = Math.max(1,parseInt(req.query.page)||1), size = 12
      res.json({total:filtered.length,page,page_size:size,items:filtered.slice((page-1)*size,page*size).map(({annotations,videos,...r}) => ({...r, instruction:annotations.en[0] || ''}))})
    } catch(e) {next(e)}
  })
  app.get('/api/episodes/:id', async (req,res,next) => {
    try { const {rows}=await catalog(); const r=rows.find(r=>r.episode_index===Number(req.params.id)); r ? res.json(r) : res.status(404).json({error:'Episode not found'}) } catch(e) {next(e)}
  })
  app.get('/api/thumbnails/:id/:camera', async (req,res,next) => {
    try {
      const {rows} = await catalog()
      const record = rows.find(r => r.episode_index === Number(req.params.id))
      const camera = req.params.camera
      if (!record || !['head','chest'].includes(camera)) return res.status(404).json({error:'Preview not found'})
      const source = path.join(dataDir, record.videos[camera].replace('/dataset/', ''))
      const file = await thumbnail(source)
      res.set('Cache-Control','public, max-age=3600').sendFile(file)
    } catch (e) { next(e) }
  })
  app.use('/dataset/assets',express.static(path.join(dataDir,'assets'),{dotfiles:'deny',fallthrough:false}))
  app.use((err,req,res,next) => { res.status(err.status===404?404:503).json({error:err.status===404?'Media not found':'Dataset unavailable. Check the dataset directory and ready index, then retry.'}) })
  return app
}

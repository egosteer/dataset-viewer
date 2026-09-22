import express from 'express'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createDatasetApp } from './api.js'
if (process.env.NODE_ENV === 'production') throw new Error('This server is local-debug only. Publish dist/ on GitHub Pages.')
const app=createDatasetApp()
app.use(express.static(path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist')))
const port=Number(process.env.PORT)||4173
app.listen(port,'127.0.0.1',()=>console.log(`Local debug API: http://127.0.0.1:${port} (use npm run debug for the local-data UI)`))

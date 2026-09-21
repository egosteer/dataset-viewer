import express from 'express'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createDatasetApp } from './api.js'
const app=createDatasetApp()
app.use(express.static(path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist')))
const port=Number(process.env.PORT)||4173
app.listen(port,'127.0.0.1',()=>console.log(`EgoSteer browser: http://127.0.0.1:${port}`))

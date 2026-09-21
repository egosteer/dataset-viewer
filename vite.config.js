import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createDatasetApp } from './server/api.js'
export default defineConfig({plugins:[vue(),{name:'dataset-api',configureServer(server){server.middlewares.use(createDatasetApp())},configurePreviewServer(server){server.middlewares.use(createDatasetApp())}}]})

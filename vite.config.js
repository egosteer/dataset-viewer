import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig(({ command, mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const local = mode === 'debug' || env.VITE_DATA_SOURCE === 'local'
  if (command === 'build' && local) throw new Error('Local dataset API is debug-only. Build with COS data mode.')
  return {
    // Relative asset/worker URLs also work under /dataset-viewer/ on GitHub Pages.
    base: './',
    define: { 'import.meta.env.VITE_DATA_SOURCE': JSON.stringify(local ? 'local' : 'cos') },
    plugins: [vue(), ...(local ? [{
      name: 'local-debug-dataset-api',
      async configureServer(server) {
        const { createDatasetApp } = await import('./server/api.js')
        server.middlewares.use(createDatasetApp(env.DATASET_DIR))
      },
    }] : [])],
  }
})

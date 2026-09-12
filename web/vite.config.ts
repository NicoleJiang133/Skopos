import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // the SDK loads its wasm via a relative dynamic import; pre-bundling breaks that path
  optimizeDeps: {
    exclude: ['@reactor-team/js-sdk', '@reactor-models/visko-orbis-stable'],
    include: ['awaitqueue', 'hls.js', 'mp4box'],
  },
  server: {
    host: true,
    proxy: {
      '/api': { target: 'http://localhost:8787', changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})

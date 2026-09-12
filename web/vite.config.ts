import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const BACKEND = process.env.SKOPOS_BACKEND ?? 'http://127.0.0.1:8000'

// Serves the game backend's page at /play. Its client hardcodes `ws://` for the
// /ws socket, which browsers block on https pages, so the scheme is patched here.
// "End session" is also routed back to the frontend's Finish screen (/#finish).
const FINISH_HOOK = `<script>addEventListener('DOMContentLoaded',()=>{const b=document.getElementById('rx-end');if(!b)return;const prev=b.onclick;b.onclick=e=>{try{prev&&prev.call(b,e)}finally{location.assign('/#finish')}}})</script></body>`
function playPage(): Plugin {
  return {
    name: 'skopos-play-page',
    configureServer(server) {
      server.middlewares.use('/play', async (_req, res) => {
        const upstream = await fetch(`${BACKEND}/`)
        const html = (await upstream.text())
          .replace(
            'new WebSocket(`ws://${location.host}/ws`)',
            "new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)",
          )
          .replace('</body>', FINISH_HOOK)
        res.setHeader('content-type', 'text/html; charset=utf-8')
        res.statusCode = upstream.status
        res.end(html)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), playPage()],
  // the SDK loads its wasm via a relative dynamic import; pre-bundling breaks that path
  optimizeDeps: {
    exclude: ['@reactor-team/js-sdk', '@reactor-models/visko-orbis-stable'],
    include: ['awaitqueue', 'hls.js', 'mp4box'],
  },
  server: {
    host: true,
    // order matters: first matching prefix wins
    proxy: {
      '/api/token': {
        target: 'http://localhost:8787',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/api/session': {
        target: 'http://localhost:8787',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      // game backend (msimakhov-star/Skopos@local-build); its page is served at /play by playPage()
      '/api': { target: BACKEND, changeOrigin: true },
      '/static': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
})

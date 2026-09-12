// Exchanges the server-side Reactor key (rk_...) for a short-lived client JWT
// (POST https://api.reactor.inc/tokens, header Reactor-API-Key). The rk_ key
// never reaches the browser. Run: REACTOR_API_KEY=rk_... node server/token.mjs
import { createServer } from 'node:http'

const PORT = Number(process.env.PORT ?? 8787)
const REACTOR_API_KEY = process.env.REACTOR_API_KEY
const REACTOR_API_URL = process.env.REACTOR_API_URL ?? 'https://api.reactor.inc'

const MODELS = (process.env.REACTOR_MODELS ?? 'reactor/visko-orbis-stable').split(',')

// Scope the JWT to our models only, so a leaked token can't drive anything else.
const SCOPE = {
  authorization_details: [
    {
      type: 'session',
      resources: { models: { match: MODELS } },
      constraints: { max_sessions: 3, max_session_duration_seconds: 3600 },
    },
  ],
}

const json = (res, status, body) =>
  res.writeHead(status, { 'content-type': 'application/json' }).end(JSON.stringify(body))

createServer(async (req, res) => {
  res.setHeader('access-control-allow-origin', '*')
  res.setHeader('access-control-allow-headers', 'content-type')
  res.setHeader('access-control-allow-methods', 'POST, OPTIONS')
  if (req.method === 'OPTIONS') return res.writeHead(204).end()
  if (!REACTOR_API_KEY) return json(res, 503, { error: 'REACTOR_API_KEY not configured' })

  // Ends a session server-side. The account allows one concurrent Visko session,
  // so a page reload must free the old one or the next connect 429s.
  const release = req.url?.match(/^\/session\/([\w-]+)$/)
  if (req.method === 'POST' && release) {
    const up = await fetch(`${REACTOR_API_URL}/sessions/${release[1]}`, {
      method: 'DELETE',
      headers: { 'Reactor-API-Key': REACTOR_API_KEY },
    })
    return json(res, up.ok ? 200 : up.status, { released: up.ok })
  }

  if (req.method !== 'POST' || req.url !== '/token') return res.writeHead(404).end()

  try {
    const upstream = await fetch(`${REACTOR_API_URL}/tokens`, {
      method: 'POST',
      headers: { 'Reactor-API-Key': REACTOR_API_KEY, 'content-type': 'application/json' },
      body: JSON.stringify(SCOPE),
    })
    const text = await upstream.text()
    if (!upstream.ok) {
      console.error('token mint failed', upstream.status, text.slice(0, 200))
      return json(res, upstream.status, { error: 'token mint failed' })
    }
    const { jwt, expires_at } = JSON.parse(text)
    json(res, 200, { jwt, expires_at })
  } catch (err) {
    json(res, 502, { error: String(err) })
  }
}).listen(PORT, () => console.log(`token server on :${PORT}`))

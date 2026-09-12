import { ViskoOrbisStableModel } from '@reactor-models/visko-orbis-stable'
import type { BedState } from '../prompts/types'

export type BedSourceKind = 'live' | 'clip' | 'procedural'

export interface ViskoHandle {
  model: ViskoOrbisStableModel
  /** fires with main_video — immediately if the track already exists */
  onVideo: (cb: (stream: MediaStream) => void) => () => void
  setPrompt: (prompt: string) => void
  /** anchors the first chunk; only honoured before start / after reset */
  setImage: (url: string) => Promise<void>
  start: () => Promise<void>
  close: () => Promise<void>
}

const API_BASE = import.meta.env.VITE_TOKEN_API ?? '/api'
const SESSION_KEY = 'skopos.visko.session'

/** Free the last session this tab held (survives reloads via sessionStorage). */
async function releaseStaleSession() {
  const id = sessionStorage.getItem(SESSION_KEY)
  if (!id) return
  sessionStorage.removeItem(SESSION_KEY)
  await fetch(`${API_BASE}/session/${id}`, { method: 'POST' }).catch(() => undefined)
}

async function mintJwt(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/token`, { method: 'POST' })
    if (!res.ok) return null
    const { jwt } = (await res.json()) as { jwt?: string }
    return jwt ?? null
  } catch {
    return null
  }
}

/**
 * One Visko session is the whole product's world. The rk_ key stays on the
 * token server; the browser only ever sees a short-lived JWT.
 */
// connects are serialised so a StrictMode/HMR double-mount can't race the 1-session quota
let queue: Promise<unknown> = Promise.resolve()

export function openViskoSession(
  onError: (message: string) => void,
): Promise<ViskoHandle | null> {
  const next = queue.then(() => connectVisko(onError))
  queue = next.catch(() => undefined)
  return next
}

async function connectVisko(
  onError: (message: string) => void,
): Promise<ViskoHandle | null> {
  await releaseStaleSession()
  const jwt = await mintJwt()
  if (!jwt) return null

  const model = new ViskoOrbisStableModel()
  if (import.meta.env.DEV) (window as unknown as { __visko: unknown }).__visko = model
  model.on('error', (err: unknown) => onError(err instanceof Error ? err.message : String(err)))
  model.on('statusChanged', (status) => {
    if (status === 'disconnected') onError('session disconnected')
  })
  model.onCommandError((m) => onError(`${m.command}: ${m.reason}`))

  try {
    await model.connect(jwt)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
    return null
  }

  // the account allows one concurrent Visko session: release it on reload/close.
  // sendBeacon survives unload where the SDK's own disconnect may not finish.
  const sessionId = model.getSessionId()
  if (sessionId) sessionStorage.setItem(SESSION_KEY, sessionId)
  const release = () => {
    if (sessionId) navigator.sendBeacon(`${API_BASE}/session/${sessionId}`)
    sessionStorage.removeItem(SESSION_KEY)
  }
  window.addEventListener('pagehide', release)

  return {
    model,
    onVideo: (cb) => {
      const existing = model.getStreamByName('main_video')
      if (existing) cb(existing)
      return model.onMainVideo((_track, stream) => cb(stream))
    },
    setPrompt: (prompt) => {
      void model.setPrompt({ prompt })
    },
    setImage: async (url) => {
      const blob = await (await fetch(url)).blob()
      const ref = await model.uploadFile(blob, { name: url.split('/').pop() ?? 'anchor' })
      await model.setImage({ image: ref })
    },
    start: async () => {
      await model.start()
    },
    close: async () => {
      window.removeEventListener('pagehide', release)
      sessionStorage.removeItem(SESSION_KEY)
      await model.disconnect()
    },
  }
}

/** One Visko chunk is 33 frames at 18fps; the world answers at that cadence. */
export const CHUNK_MS = 1830

export function debouncePrompt(fn: (prompt: string, state: BedState) => void) {
  let timer: number | undefined
  return (prompt: string, state: BedState) => {
    if (timer) window.clearTimeout(timer)
    timer = window.setTimeout(() => fn(prompt, state), 220)
  }
}

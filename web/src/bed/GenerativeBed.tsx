import { useEffect, useRef, useState } from 'react'
import { composePhotoPrompt } from '../prompts/photoWorld'
import { programs } from '../prompts/screens'
import { useStore } from '../state/store'
import { startPhotoBed } from './photoBed'
import { startProceduralBed } from './proceduralBed'
import {
  debouncePrompt,
  openViskoSession,
  type BedSourceKind,
  type ViskoHandle,
} from './viskoSession'

/**
 * The persistent "game world" behind the whole product. One session, one
 * continuous morph: screens change the prompt program, never the connection.
 */
const RETRY_MS = 20_000
const RETRY_MAX = 12

export function GenerativeBed() {
  const screen = useStore((s) => s.screen)
  const bedState = useStore((s) => s.bedState)
  const bedNudge = useStore((s) => s.bedNudge)
  const live = useStore((s) => s.live)
  const venuePhoto = useStore((s) => s.venuePhoto)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const photoCanvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const handleRef = useRef<ViskoHandle | null>(null)
  const [source, setSource] = useState<BedSourceKind>('procedural')
  const [photoReady, setPhotoReady] = useState(false)
  const [lastPrompt, setLastPrompt] = useState('')

  const program = programs[screen]

  // procedural bed always runs underneath as the zero-dependency fallback
  useEffect(() => {
    if (!canvasRef.current) return
    return startProceduralBed(canvasRef.current, () => ({
      hue: programs[useStore.getState().screen].hue,
      state: useStore.getState().bedState,
    }))
  }, [])

  useEffect(() => {
    const canvas = photoCanvasRef.current
    if (!venuePhoto || !canvas) {
      setPhotoReady(false)
      return
    }

    setPhotoReady(false)
    const url = URL.createObjectURL(venuePhoto)
    const image = new Image()
    let stopPhotoBed: (() => void) | undefined
    let cancelled = false

    image.onload = () => {
      if (cancelled) return
      stopPhotoBed = startPhotoBed(canvas, image, () => ({
        state: useStore.getState().bedState,
        hue: programs[useStore.getState().screen].hue,
      }))
      URL.revokeObjectURL(url)
      setPhotoReady(true)
      useStore.getState().pushEvent('World built from your venue photo')
    }
    image.src = url

    return () => {
      cancelled = true
      stopPhotoBed?.()
      if (!image.complete) {
        image.onload = null
        image.src = ''
        URL.revokeObjectURL(url)
      }
    }
  }, [venuePhoto])

  useEffect(() => {
    if (!live) {
      void handleRef.current?.close()
      handleRef.current = null
      setSource('procedural')
      return
    }
    let cancelled = false
    let retry: number | undefined
    const push = (t: string) => useStore.getState().pushEvent(t, 'info')
    let fatal = false
    const connect = (attempt: number) => {
      push(attempt ? `Reconnecting to Visko (${attempt})…` : 'Connecting to Visko…')
      openViskoSession((msg) => {
        if (msg.includes('credits_depleted')) fatal = true
        push(`Visko — ${msg}`)
      })
        .then(async (handle) => {
          if (cancelled || !handle) {
            void handle?.close()
            if (!cancelled) {
              setSource('procedural')
              push(
                fatal
                  ? 'Reactor credits depleted — running fallback world (top up to go live)'
                  : 'Live bed unavailable — running fallback world',
              )
              // a stale session (one-per-account) expires on its own; keep trying
              if (!fatal && attempt < RETRY_MAX)
                retry = window.setTimeout(() => connect(attempt + 1), RETRY_MS)
            }
            return
          }
          handleRef.current = handle
          handle.onLost(() => {
            if (cancelled) return
            handleRef.current = null
            if (videoRef.current) videoRef.current.srcObject = null
            setSource('procedural')
            push('World stream lost — running fallback, reconnecting')
            retry = window.setTimeout(() => connect(1), RETRY_MS)
          })
          handle.onVideo((stream) => {
            if (videoRef.current) {
              videoRef.current.srcObject = stream
              void videoRef.current.play().catch(() => undefined)
            }
            setSource('live')
            push('Visko session live — world streaming')
          })
          const s = useStore.getState()
          const prog = programs[s.screen]
          const photo = s.venuePhoto
          if (photo) await handle.prime(photo)
          handle.setPrompt(
            photo ? composePhotoPrompt(s.screen, s.bedState) : prog.composePrompt(s.bedState),
          )
          await handle.start()
        })
        .catch((err: unknown) => {
          setSource('procedural')
          push(`Visko failed — ${err instanceof Error ? err.message : String(err)}`)
        })
    }
    connect(0)
    return () => {
      cancelled = true
      window.clearTimeout(retry)
      void handleRef.current?.close()
      handleRef.current = null
    }
  }, [live])

  // event bus: store state -> debounced set_prompt / set_image
  useEffect(() => {
    const send = debouncePrompt((prompt) => {
      setLastPrompt(prompt)
      handleRef.current?.setPrompt(prompt)
    })
    const base = venuePhoto ? composePhotoPrompt(screen, bedState) : program.composePrompt(bedState)
    send(bedNudge ? `${base} ${bedNudge}.` : base, bedState)
  }, [program, bedState, bedNudge, venuePhoto])

  useEffect(() => {
    if (!handleRef.current || !venuePhoto) return
    const base = composePhotoPrompt(screen, bedState)
    const prompt = bedNudge ? `${base} ${bedNudge}.` : base
    void handleRef.current.anchor(venuePhoto, prompt)
    useStore.getState().pushEvent('World re-anchored to your venue photo')
  }, [venuePhoto])

  const shown: BedSourceKind = source === 'live' ? 'live' : photoReady ? 'photo' : 'procedural'

  return (
    <div className="sk-scanlines" style={{ position: 'fixed', inset: 0, zIndex: 0 }}>
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          opacity: shown === 'procedural' ? 1 : 0,
          transition: 'opacity var(--sk-dur-morph) var(--sk-ease)',
        }}
      />
      <canvas
        ref={photoCanvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          opacity: shown === 'photo' ? 1 : 0,
          transition: 'opacity var(--sk-dur-morph) var(--sk-ease)',
        }}
      />
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          opacity: shown === 'live' ? 1 : 0,
          transition: 'opacity var(--sk-dur-morph) var(--sk-ease)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(ellipse 70% 60% at 50% 50%, rgba(20,17,13,0.55), rgba(20,17,13,0.2) 70%, rgba(20,17,13,0.45))',
        }}
      />
      <BedDebug source={shown} prompt={lastPrompt} anchor={program.anchor} />
    </div>
  )
}

function BedDebug({
  source,
  prompt,
  anchor,
}: {
  source: BedSourceKind
  prompt: string
  anchor: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <div
      style={{
        position: 'absolute',
        left: 16,
        bottom: 16,
        maxWidth: 420,
        zIndex: 3,
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="sk-panel"
        style={{
          font: '11px var(--sk-font-mono)',
          color: 'var(--sk-text-dim)',
          padding: '6px 10px',
          cursor: 'pointer',
        }}
      >
        bed: {source} {open ? '▾' : '▸'}
      </button>
      {open && (
        <div
          className="sk-panel"
          style={{
            marginTop: 8,
            padding: 10,
            font: '10px/1.5 var(--sk-font-mono)',
            color: 'var(--sk-text-dim)',
          }}
        >
          <div style={{ color: 'var(--sk-cyan)' }}>anchor: {anchor}</div>
          <div style={{ marginTop: 6 }}>{prompt}</div>
        </div>
      )}
    </div>
  )
}

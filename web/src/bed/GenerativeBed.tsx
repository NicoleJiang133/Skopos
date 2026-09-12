import { useEffect, useRef, useState } from 'react'
import { programs } from '../prompts/screens'
import { useStore } from '../state/store'
import { startProceduralBed } from './proceduralBed'
import { debouncePrompt, openViskoSession, type BedSourceKind, type ViskoHandle } from './viskoSession'

/**
 * The persistent "game world" behind the whole product. One session, one
 * continuous morph: screens change the prompt program, never the connection.
 */
export function GenerativeBed() {
  const screen = useStore((s) => s.screen)
  const bedState = useStore((s) => s.bedState)
  const bedNudge = useStore((s) => s.bedNudge)
  const live = useStore((s) => s.live)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const handleRef = useRef<ViskoHandle | null>(null)
  const [source, setSource] = useState<BedSourceKind>('procedural')
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
    if (!live) {
      void handleRef.current?.close()
      handleRef.current = null
      setSource('procedural')
      return
    }
    let cancelled = false
    const push = (t: string) => useStore.getState().pushEvent(t, 'info')
    push('Connecting to Visko…')
    openViskoSession((msg) => push(`Visko — ${msg}`))
      .then(async (handle) => {
        if (cancelled || !handle) {
          void handle?.close()
          if (!cancelled) {
            setSource('procedural')
            push('Live bed unavailable — running fallback world')
          }
          return
        }
        handleRef.current = handle
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
        handle.setPrompt(prog.composePrompt(s.bedState))
        await handle.start()
      })
      .catch((err: unknown) => {
        setSource('procedural')
        push(`Visko failed — ${err instanceof Error ? err.message : String(err)}`)
      })
    return () => {
      cancelled = true
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
    const base = program.composePrompt(bedState)
    send(bedNudge ? `${base} ${bedNudge}.` : base, bedState)
  }, [program, bedState, bedNudge])

  return (
    <div className="sk-scanlines" style={{ position: 'fixed', inset: 0, zIndex: 0 }}>
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          opacity: source === 'live' ? 0 : 1,
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
          opacity: source === 'live' ? 1 : 0,
          transition: 'opacity var(--sk-dur-morph) var(--sk-ease)',
        }}
      />
      <BedDebug source={source} prompt={lastPrompt} anchor={program.anchor} />
    </div>
  )
}

function BedDebug({ source, prompt, anchor }: { source: BedSourceKind; prompt: string; anchor: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ position: 'absolute', left: 16, bottom: 16, maxWidth: 420, zIndex: 3 }}>
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

import { useEffect, useRef, useState } from 'react'
import { programs } from '../prompts/screens'
import { useStore } from '../state/store'
import { debouncePrompt, type BedSourceKind } from './bedBus'
import { startPhotoBed } from './photoBed'
import { startProceduralBed } from './proceduralBed'

/**
 * The living world behind the whole product. The venue photo is the primary
 * layer; the procedural canvas remains available when no photo is loaded.
 */
export function GenerativeBed() {
  const screen = useStore((s) => s.screen)
  const bedState = useStore((s) => s.bedState)
  const bedNudge = useStore((s) => s.bedNudge)
  const venuePhoto = useStore((s) => s.venuePhoto)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const photoCanvasRef = useRef<HTMLCanvasElement>(null)
  const [source, setSource] = useState<BedSourceKind>('procedural')
  const [worldNote, setWorldNote] = useState('')

  const program = programs[screen]

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
      setSource('procedural')
      return
    }

    setSource('procedural')
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
      setSource('photo')
      useStore.getState().pushEvent('World built from your venue photo')
    }
    image.src = url

    return () => {
      cancelled = true
      stopPhotoBed?.()
      URL.revokeObjectURL(url)
    }
  }, [venuePhoto])

  // World state -> debounced debug description.
  useEffect(() => {
    const send = debouncePrompt((note) => setWorldNote(note))
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
          opacity: source === 'procedural' ? 1 : 0,
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
          opacity: source === 'photo' ? 1 : 0,
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
      <BedDebug source={source} note={worldNote} />
    </div>
  )
}

function BedDebug({ source, note }: { source: BedSourceKind; note: string }) {
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
          <div>{note}</div>
        </div>
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { CTA } from '../hud/HudChrome'
import { enterBackend, scanVenue } from '../backend/handoff'
import { useStore } from '../state/store'

export function Landing() {
  const goto = useStore((s) => s.goto)
  const venuePhoto = useStore((s) => s.venuePhoto)
  const setVenuePhoto = useStore((s) => s.setVenuePhoto)
  const logInteraction = useStore((s) => s.logInteraction)
  const pushEvent = useStore((s) => s.pushEvent)
  const inputRef = useRef<HTMLInputElement>(null)
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const [handoff, setHandoff] = useState<'idle' | 'scanning' | 'success' | 'error'>('idle')
  const [handoffMessage, setHandoffMessage] = useState('')

  const enterVenue = async () => {
    if (!venuePhoto || handoff === 'scanning' || handoff === 'success') return
    setHandoff('scanning')
    setHandoffMessage('')
    const name = (venuePhoto as File).name ?? 'photo'
    logInteraction('enter_backend', { bytes: venuePhoto.size, name })
    try {
      const result = await scanVenue(venuePhoto)
      const message = `Found ${result.objects.length} objects in your venue — entering…`
      setHandoffMessage(message)
      setHandoff('success')
      pushEvent(message)
      window.setTimeout(enterBackend, 800)
    } catch (error) {
      setHandoffMessage(error instanceof Error ? error.message : String(error))
      setHandoff('error')
    }
  }

  useEffect(() => {
    if (!venuePhoto) {
      setPhotoUrl(null)
      return
    }
    const url = URL.createObjectURL(venuePhoto)
    setPhotoUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [venuePhoto])

  return (
    <div
      style={{
        height: '100%',
        display: 'grid',
        placeItems: 'center',
        textAlign: 'center',
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 620 }}>
        <div
          style={{
            font: '12px var(--sk-font-mono)',
            letterSpacing: 6,
            color: 'var(--sk-cyan)',
            animation: 'sk-breathe 3.4s var(--sk-ease) infinite',
          }}
        >
          SKOPOS
        </div>
        <h1 style={{ fontSize: 46, lineHeight: 1.1, margin: '18px 0 14px', fontWeight: 500 }}>
          Define how your robots behave in your venue — and keep it true when the floor moves.
        </h1>
        <p style={{ color: 'var(--sk-text-dim)', fontSize: 15, marginBottom: 30 }}>
          Upload a photo of your space, then play inside it — every table you move and route you
          pick teaches Skopos how you like your robots to work.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) {
              setHandoff('idle')
              setHandoffMessage('')
              setVenuePhoto(file)
            }
          }}
        />
        <button
          className="sk-panel"
          onClick={() => inputRef.current?.click()}
          style={{
            font: '12px var(--sk-font-mono)',
            padding: '10px 16px',
            color: 'var(--sk-text)',
            cursor: 'pointer',
          }}
        >
          Upload a photo of your venue
        </button>
        <div
          style={{
            marginTop: 10,
            font: '11px var(--sk-font-mono)',
            color: 'var(--sk-text-dim)',
          }}
        >
          {venuePhoto
            ? 'Step 2 — enter and play as the robot in your venue.'
            : 'Step 1 — upload a photo of your physical venue. We build your world from it.'}
        </div>
        {photoUrl && (
          <div style={{ marginTop: 14 }}>
            <img
              src={photoUrl}
              alt="Venue preview"
              style={{ height: 96, maxWidth: '100%', objectFit: 'cover' }}
            />
            <div
              style={{
                marginTop: 6,
                font: '11px var(--sk-font-mono)',
                color: 'var(--sk-text-dim)',
              }}
            >
              Your venue becomes the world
            </div>
          </div>
        )}
        <div style={{ marginTop: 24 }}>
          <CTA
            disabled={!venuePhoto || handoff === 'scanning' || handoff === 'success'}
            onClick={enterVenue}
          >
            {!venuePhoto
              ? 'Set up this venue'
              : handoff === 'scanning'
                ? 'Building your world…'
                : 'Enter your venue'}
          </CTA>
        </div>
        {handoffMessage && (
          <div
            style={{
              marginTop: 10,
              font: '11px var(--sk-font-mono)',
              color: handoff === 'error' ? 'var(--sk-amber)' : 'var(--sk-text-dim)',
            }}
          >
            {handoffMessage}
          </div>
        )}
        {handoff === 'error' && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              gap: 12,
              marginTop: 10,
              font: '11px var(--sk-font-mono)',
            }}
          >
            <button
              onClick={enterVenue}
              style={{
                border: '1px solid var(--sk-amber)',
                background: 'transparent',
                color: 'var(--sk-amber)',
                padding: '5px 9px',
                font: 'inherit',
                cursor: 'pointer',
              }}
            >
              Retry
            </button>
            <button
              onClick={() => goto('setup')}
              style={{
                border: 0,
                padding: 0,
                background: 'transparent',
                color: 'var(--sk-text-dim)',
                font: 'inherit',
                textDecoration: 'underline',
                cursor: 'pointer',
              }}
            >
              Open Setup instead
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

import { useEffect, useMemo, useRef } from 'react'
import { useStore } from '../state/store'
import { CTA } from '../hud/HudChrome'

export function Landing() {
  const goto = useStore((s) => s.goto)
  const venuePhoto = useStore((s) => s.venuePhoto)
  const setVenuePhoto = useStore((s) => s.setVenuePhoto)
  const inputRef = useRef<HTMLInputElement>(null)
  const photoUrl = useMemo(
    () => (venuePhoto ? URL.createObjectURL(venuePhoto) : null),
    [venuePhoto],
  )

  useEffect(() => {
    return () => {
      if (photoUrl) URL.revokeObjectURL(photoUrl)
    }
  }, [photoUrl])

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
            if (file) setVenuePhoto(file)
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
              World will be generated from this photo
            </div>
          </div>
        )}
        <div style={{ marginTop: 24 }}>
          <CTA onClick={() => goto('setup')}>
            {venuePhoto ? 'Enter your venue' : 'Set up this venue'}
          </CTA>
        </div>
      </div>
    </div>
  )
}

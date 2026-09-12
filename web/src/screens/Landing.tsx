import { useStore } from '../state/store'
import { CTA } from '../hud/HudChrome'

export function Landing() {
  const goto = useStore((s) => s.goto)
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
          Cleaning and serving robots, operated from one live plan of your space.
        </p>
        <CTA onClick={() => goto('setup')}>Set up this venue</CTA>
      </div>
    </div>
  )
}

import { useStore } from '../state/store'
import { Panel } from './HudChrome'

const TONE: Record<string, string> = {
  info: 'var(--sk-text-dim)',
  action: 'var(--sk-amber)',
  plan: 'var(--sk-teal)',
}

export function EventFeed() {
  const events = useStore((s) => s.events)
  return (
    <Panel title="Event stream" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ overflowY: 'auto', display: 'grid', gap: 6, paddingRight: 4 }}>
        {events.map((e) => (
          <div key={e.id} style={{ font: '11px/1.5 var(--sk-font-mono)', color: TONE[e.tone] }}>
            <span style={{ opacity: 0.5 }}>
              {new Date(e.at).toLocaleTimeString([], { hour12: false })}
            </span>{' '}
            {e.text}
          </div>
        ))}
      </div>
      <div style={{ font: '10px var(--sk-font-mono)', color: 'var(--sk-text-dim)', marginTop: 10, opacity: 0.7 }}>
        Planning is real (local A*). The world view is a generated simulation.
      </div>
    </Panel>
  )
}

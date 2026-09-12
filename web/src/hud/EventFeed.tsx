import { useStore } from '../state/store'
import { Panel } from './HudChrome'

const TONE: Record<string, string> = {
  info: 'var(--sk-text-dim)',
  action: 'var(--sk-amber)',
  plan: 'var(--sk-teal)',
}

export function EventFeed() {
  const events = useStore((s) => s.events)
  const interactions = useStore((s) => s.interactions)
  const exportInteractions = useStore((s) => s.exportInteractions)
  return (
    <Panel
      title="Event stream"
      style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
    >
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
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 8,
          font: '10px var(--sk-font-mono)',
          color: 'var(--sk-text-dim)',
          marginTop: 10,
          opacity: 0.7,
        }}
      >
        <span>Planning is real (local A*). The world is your venue photo.</span>
        <button
          onClick={exportInteractions}
          style={{
            border: 0,
            padding: 0,
            background: 'transparent',
            color: 'var(--sk-teal)',
            font: 'inherit',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          ground truth · {interactions.length} · export
        </button>
      </div>
    </Panel>
  )
}

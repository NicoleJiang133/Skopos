import { useStore } from '../state/store'
import { Panel } from './HudChrome'

export function JobCards() {
  const jobs = useStore((s) => s.jobs)
  const activeJobId = useStore((s) => s.activeJobId)
  const selectJob = useStore((s) => s.selectJob)
  const replanning = useStore((s) => s.replanning)

  return (
    <Panel title="Tasks">
      <div style={{ display: 'grid', gap: 8 }}>
        {jobs.map((j) => {
          const active = j.id === activeJobId
          const color = j.kind === 'serve' ? 'var(--sk-amber)' : 'var(--sk-teal)'
          return (
            <button
              key={j.id}
              onClick={() => selectJob(j.id)}
              style={{
                textAlign: 'left',
                border: `1px solid ${active ? color : 'var(--sk-edge)'}`,
                background: active ? `color-mix(in srgb, ${color} 12%, transparent)` : 'transparent',
                borderRadius: 'var(--sk-radius-sm)',
                padding: '10px 12px',
                color: 'var(--sk-text)',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontSize: 13 }}>{j.label}</div>
              <div style={{ font: '10px var(--sk-font-mono)', color, marginTop: 4 }}>
                {active && replanning ? 'replanning…' : j.status}
              </div>
            </button>
          )
        })}
      </div>
    </Panel>
  )
}

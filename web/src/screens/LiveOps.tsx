import { useEffect } from 'react'
import { GridView } from '../floor/GridView'
import { EventFeed } from '../hud/EventFeed'
import { JobCards } from '../hud/JobCards'
import { Panel } from '../hud/HudChrome'
import { useStore } from '../state/store'

export function LiveOps() {
  const activeJob = useStore((s) => s.jobs.find((j) => j.id === s.activeJobId))
  const heading = useStore((s) => s.heading)
  const trail = useStore((s) => s.trail)
  const route = useStore((s) => s.route)
  const interactions = useStore((s) => s.interactions)
  const driveRobot = useStore((s) => s.driveRobot)
  const offRoute = interactions.filter(
    (interaction) => interaction.kind === 'drive' && interaction.detail.onRoute === 0,
  ).length
  const compass = ['N', 'E', 'S', 'W'][heading]

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement
      )
        return

      const key = event.key.toLowerCase()
      const action =
        key === 'arrowup' || key === 'w'
          ? 'forward'
          : key === 'arrowleft' || key === 'a'
            ? 'left'
            : key === 'arrowright' || key === 'd'
              ? 'right'
              : null
      if (!action) return
      event.preventDefault()
      driveRobot(action)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [driveRobot])

  return (
    <div style={{ position: 'relative', height: '100%', overflow: 'hidden' }}>
      <div
        style={{
          position: 'absolute',
          top: 18,
          left: '50%',
          transform: 'translateX(-50%)',
          font: '11px var(--sk-font-mono)',
          color: 'var(--sk-text-dim)',
          whiteSpace: 'nowrap',
        }}
      >
        You are the robot. Drive to: {activeJob?.label ?? 'your next task'}
      </div>

      <div
        style={{
          position: 'absolute',
          top: 20,
          right: 20,
          bottom: 20,
          width: 260,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          minHeight: 0,
        }}
      >
        <JobCards />
        <EventFeed />
      </div>

      <div style={{ position: 'absolute', left: 20, bottom: 20 }}>
        <Panel title="Minimap" style={{ padding: 12 }}>
          <GridView cell={12} editable={false} showLabels={false} trail={trail} heading={heading} />
        </Panel>
      </div>

      <div
        className="sk-panel"
        style={{
          position: 'absolute',
          left: '50%',
          bottom: 20,
          transform: 'translateX(-50%)',
          padding: '10px 14px',
          textAlign: 'center',
          font: '11px var(--sk-font-mono)',
          color: 'var(--sk-text-dim)',
        }}
      >
        <div style={{ color: 'var(--sk-text)', marginBottom: 8 }}>
          ▲ forward&nbsp;&nbsp; ◀ ▶ turn
        </div>
        <div>facing {compass}</div>
        <div style={{ marginTop: 6 }}>
          walked {trail.length - 1} · suggested {Math.max(0, route.length - 1)} · off-route{' '}
          {offRoute}
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginTop: 10 }}>
          <button
            onClick={() => driveRobot('left')}
            aria-label="Turn left"
            style={controlButtonStyle}
          >
            ◀
          </button>
          <button
            onClick={() => driveRobot('forward')}
            aria-label="Drive forward"
            style={controlButtonStyle}
          >
            ▲
          </button>
          <button
            onClick={() => driveRobot('right')}
            aria-label="Turn right"
            style={controlButtonStyle}
          >
            ▶
          </button>
        </div>
      </div>
    </div>
  )
}

const controlButtonStyle: React.CSSProperties = {
  border: '1px solid var(--sk-edge)',
  background: 'rgba(242,198,109,0.08)',
  color: 'var(--sk-text)',
  width: 30,
  height: 26,
  cursor: 'pointer',
  font: '14px var(--sk-font-mono)',
}

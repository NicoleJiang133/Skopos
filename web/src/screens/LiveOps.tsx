import { useEffect } from 'react'
import { GridView } from '../floor/GridView'
import { EventFeed } from '../hud/EventFeed'
import { JobCards } from '../hud/JobCards'
import { Panel } from '../hud/HudChrome'
import { useStore } from '../state/store'

export function LiveOps() {
  const tickRobot = useStore((s) => s.tickRobot)
  const replanning = useStore((s) => s.replanning)
  const route = useStore((s) => s.route)
  const progress = useStore((s) => s.routeProgress)

  useEffect(() => {
    const id = window.setInterval(tickRobot, 700)
    return () => window.clearInterval(id)
  }, [tickRobot])

  return (
    <div
      style={{
        height: '100%',
        display: 'grid',
        gridTemplateColumns: '1fr 300px',
        gap: 20,
        padding: 24,
      }}
    >
      <div style={{ display: 'grid', justifyItems: 'center', alignContent: 'center', gap: 12 }}>
        <Panel title="Floor — live" style={{ padding: 16 }}>
          <GridView cell={30} editable showLabels={false} />
          <div
            style={{
              font: '11px var(--sk-font-mono)',
              color: replanning ? 'var(--sk-teal)' : 'var(--sk-text-dim)',
              marginTop: 10,
            }}
          >
            {replanning
              ? 'floor changed — replanning route…'
              : `route ${Math.min(progress + 1, route.length)}/${route.length} cells · drag any table to disturb the floor`}
          </div>
        </Panel>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0 }}>
        <JobCards />
        <EventFeed />
      </div>
    </div>
  )
}

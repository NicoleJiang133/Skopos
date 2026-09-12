import { GridView } from '../floor/GridView'
import { InventoryTray } from '../floor/InventoryTray'
import { CTA } from '../hud/HudChrome'
import { useStore } from '../state/store'

export function Setup() {
  const goto = useStore((s) => s.goto)
  const grid = useStore((s) => s.grid)
  return (
    <div
      style={{
        height: '100%',
        display: 'grid',
        gridTemplateColumns: '240px 1fr',
        gap: 20,
        padding: 24,
        alignItems: 'start',
      }}
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <InventoryTray />
        <CTA onClick={() => goto('live')}>Go live</CTA>
      </div>
      <div style={{ display: 'grid', justifyItems: 'center', gap: 12 }}>
        <div style={{ font: '11px var(--sk-font-mono)', color: 'var(--sk-text-dim)', letterSpacing: 1 }}>
          {grid.name.toUpperCase()} — {grid.width}×{grid.height} CELLS · {grid.objects.length} OBJECTS
        </div>
        <GridView cell={34} editable showRoute={false} />
      </div>
    </div>
  )
}

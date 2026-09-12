import { useEffect, useState } from 'react'
import { GridView } from '../floor/GridView'
import { InventoryTray } from '../floor/InventoryTray'
import { CTA } from '../hud/HudChrome'
import { useStore } from '../state/store'

export function Setup() {
  const goto = useStore((s) => s.goto)
  const grid = useStore((s) => s.grid)
  const venuePhoto = useStore((s) => s.venuePhoto)
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const tableCount = grid.objects.filter((object) => object.type === 'table').length

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
        gridTemplateColumns: '240px 1fr',
        gap: 20,
        padding: 24,
        alignItems: 'start',
      }}
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <InventoryTray />
        <CTA disabled={Boolean(venuePhoto) && tableCount === 0} onClick={() => goto('live')}>
          Play as the robot
        </CTA>
        {venuePhoto && tableCount === 0 && (
          <div style={{ font: '11px var(--sk-font-mono)', color: 'var(--sk-text-dim)' }}>
            Place at least one table so the robot has somewhere to go
          </div>
        )}
      </div>
      <div style={{ display: 'grid', justifyItems: 'center', gap: 12 }}>
        <div
          style={{
            font: '11px var(--sk-font-mono)',
            color: 'var(--sk-text-dim)',
            letterSpacing: 1,
          }}
        >
          {venuePhoto
            ? 'Mark your venue — drag each item to where it stands in your photo'
            : `${grid.name.toUpperCase()} — ${grid.width}×${grid.height} CELLS · ${grid.objects.length} OBJECTS`}
        </div>
        <GridView cell={34} editable showRoute={false} backgroundUrl={photoUrl ?? undefined} />
      </div>
    </div>
  )
}

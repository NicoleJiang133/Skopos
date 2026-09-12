// Same-origin by default: the dev server proxies /play, /api, /static and /ws to the game backend.
export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? '/play'
const SCAN_BASE = import.meta.env.VITE_BACKEND_SCAN_BASE ?? ''

export interface ScanResult {
  roomId: string
  objects: { id: string; label: string }[]
  source: string
}

export async function scanVenue(photo: Blob): Promise<ScanResult> {
  const body = new FormData()
  body.append('file', photo, 'venue-photo.jpg')
  const response = await fetch(`${SCAN_BASE}/api/scan`, { method: 'POST', body })
  const json = (await response.json().catch(() => ({}))) as {
    error?: string
    scene?: { room_id?: string; objects?: { id?: string; label?: string }[] }
    source?: string
  }
  if (!response.ok) throw new Error(json.error ?? `scan failed (${response.status})`)
  return {
    roomId: json.scene?.room_id ?? '',
    objects: (json.scene?.objects ?? []).map((object) => ({
      id: object.id ?? '',
      label: object.label ?? '',
    })),
    source: json.source ?? '',
  }
}

export function enterBackend(): void {
  window.location.assign(BACKEND_URL)
}

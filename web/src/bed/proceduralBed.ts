import type { BedState } from '../prompts/types'

interface BedParams {
  hue: number
  state: BedState
}

interface Scene {
  sky: [string, string, string]
  sun: string
  haze: string
  ridges: string[]
  ground: [string, string]
  trees: string
  sunX: number
  sunY: number
}

/** Golden-hour open-world palettes; the bed slowly crossfades between them. */
const SCENES: Scene[] = [
  {
    sky: ['#2b3a57', '#d98a4e', '#f4d3a0'],
    sun: '#ffe2a8',
    haze: 'rgba(244,211,160,0.55)',
    ridges: ['#7d6a8a', '#5c5470', '#4a4a4f', '#3a3d36'],
    ground: ['#8a9a4c', '#4a5230'],
    trees: '#1f2418',
    sunX: 0.68,
    sunY: 0.43,
  },
  {
    sky: ['#40506b', '#c9a06a', '#f1e0b8'],
    sun: '#fff1c9',
    haze: 'rgba(241,224,184,0.5)',
    ridges: ['#8c8a9c', '#6a7080', '#4d5a55', '#3b4a3a'],
    ground: ['#a09a58', '#5a5a34'],
    trees: '#26301c',
    sunX: 0.32,
    sunY: 0.4,
  },
  {
    sky: ['#4a3e5e', '#c8714a', '#f0c48c'],
    sun: '#ffd79a',
    haze: 'rgba(240,196,140,0.5)',
    ridges: ['#8a6b78', '#6a5465', '#4f4550', '#3d3a3a'],
    ground: ['#a8804a', '#5a4630'],
    trees: '#2a2218',
    sunX: 0.5,
    sunY: 0.45,
  },
]

function ridgeY(seed: number, x: number, t: number, amp: number) {
  return (
    Math.sin(x * 1.7 + seed) * 0.55 +
    Math.sin(x * 3.9 + seed * 2.1 + t * 0.02) * 0.28 +
    Math.sin(x * 9.3 + seed * 0.7) * 0.12
  ) * amp
}

function mix(a: string, b: string, k: number) {
  const pa = parse(a)
  const pb = parse(b)
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * k))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

function parse(c: string): number[] {
  if (c.startsWith('#')) {
    const n = parseInt(c.slice(1), 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const m = c.match(/[\d.]+/g) ?? ['0', '0', '0']
  return m.slice(0, 3).map(Number)
}

/**
 * Offline stand-in for the Visko stream: a painted open-world landscape
 * (layered hills, golden-hour sky, meadow foreground) driven by the same
 * prompt-program state machine, so the bed keeps reacting without a session.
 */
export function startProceduralBed(canvas: HTMLCanvasElement, getParams: () => BedParams) {
  const ctx = canvas.getContext('2d')!
  let raf = 0
  let t = 0
  const pulses: { x: number; y: number; born: number }[] = []
  let lastState: BedState = 'idle'
  const SCENE_SECONDS = 28

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = canvas.clientWidth * dpr
    canvas.height = canvas.clientHeight * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
  resize()
  window.addEventListener('resize', resize)

  const drawScene = (scene: Scene, w: number, h: number, energy: number, alpha: number) => {
    ctx.save()
    ctx.globalAlpha = alpha
    const horizon = h * 0.58
    const drift = t * 4

    const sky = ctx.createLinearGradient(0, 0, 0, horizon)
    sky.addColorStop(0, scene.sky[0])
    sky.addColorStop(0.6, scene.sky[1])
    sky.addColorStop(1, scene.sky[2])
    ctx.fillStyle = sky
    ctx.fillRect(0, 0, w, horizon + 2)

    const sx = w * scene.sunX + Math.sin(t * 0.05) * 12
    const sy = h * scene.sunY
    const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, w * 0.45)
    glow.addColorStop(0, scene.sun)
    glow.addColorStop(0.08, scene.sun)
    glow.addColorStop(0.3, scene.haze)
    glow.addColorStop(1, 'transparent')
    ctx.fillStyle = glow
    ctx.fillRect(0, 0, w, horizon + 2)

    // distant ridges → near hills
    scene.ridges.forEach((color, i) => {
      const depth = i / (scene.ridges.length - 1)
      const base = horizon - (1 - depth) * h * 0.16
      const amp = h * (0.03 + depth * 0.06)
      ctx.beginPath()
      ctx.moveTo(0, h)
      for (let x = 0; x <= w; x += 6) {
        const nx = (x + drift * (0.2 + depth)) / w
        ctx.lineTo(x, base + ridgeY(i * 13.7, nx * 4, t, amp))
      }
      ctx.lineTo(w, h)
      ctx.closePath()
      ctx.fillStyle = mix(color, scene.sky[2], (1 - depth) * 0.45)
      ctx.fill()
    })

    // meadow foreground
    const ground = ctx.createLinearGradient(0, horizon, 0, h)
    ground.addColorStop(0, scene.ground[0])
    ground.addColorStop(1, scene.ground[1])
    ctx.fillStyle = ground
    ctx.beginPath()
    ctx.moveTo(0, h)
    for (let x = 0; x <= w; x += 6) {
      ctx.lineTo(x, horizon + h * 0.02 + ridgeY(41, ((x + drift * 1.6) / w) * 3, t, h * 0.03))
    }
    ctx.lineTo(w, h)
    ctx.closePath()
    ctx.fill()

    // clustered tree canopies along the near hill, kept away from the centre
    ctx.fillStyle = scene.trees
    for (let i = 0; i < 12; i++) {
      const px = ((i * 211 + drift * 1.6) % (w + 160)) - 80
      if (Math.abs(px - w / 2) < w * 0.22) continue
      const ny = horizon + h * 0.02 + ridgeY(41, ((px + drift * 1.6) / w) * 3, t, h * 0.03)
      const size = 26 + ((i * 53) % 30)
      ctx.beginPath()
      ctx.rect(px - 2, ny - size * 0.2, 4, size * 0.5)
      ctx.arc(px, ny - size * 0.25, size * 0.42, 0, Math.PI * 2)
      ctx.arc(px - size * 0.35, ny - size * 0.05, size * 0.3, 0, Math.PI * 2)
      ctx.arc(px + size * 0.35, ny - size * 0.02, size * 0.32, 0, Math.PI * 2)
      ctx.fill()
    }

    // low mist breathing with state
    const mist = ctx.createLinearGradient(0, horizon - h * 0.08, 0, horizon + h * 0.12)
    mist.addColorStop(0, 'transparent')
    mist.addColorStop(0.5, `rgba(244,222,190,${0.18 + 0.12 * Math.sin(t * 0.6) + energy * 0.08})`)
    mist.addColorStop(1, 'transparent')
    ctx.fillStyle = mist
    ctx.fillRect(0, horizon - h * 0.08, w, h * 0.2)
    ctx.restore()
  }

  const draw = () => {
    const { state } = getParams()
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    t += 1 / 60

    if (state !== lastState) {
      if (state === 'drag' || state === 'alert') {
        pulses.push({ x: w * (0.3 + Math.random() * 0.4), y: h * (0.6 + Math.random() * 0.3), born: t })
      }
      lastState = state
    }

    const energy =
      state === 'replanning' ? 1 : state === 'drag' ? 0.8 : state === 'enter' ? 0.9 : 0.5

    const cycle = (t / SCENE_SECONDS) % SCENES.length
    const idx = Math.floor(cycle)
    const frac = cycle - idx
    const fade = Math.max(0, (frac - 0.8) / 0.2)
    drawScene(SCENES[idx], w, h, energy, 1)
    if (fade > 0) drawScene(SCENES[(idx + 1) % SCENES.length], w, h, energy, fade)

    // dust motes
    ctx.fillStyle = 'rgba(255,236,200,0.5)'
    for (let i = 0; i < 40; i++) {
      const px = ((i * 173 + t * (6 + (i % 5) * 3)) % (w + 20)) - 10
      const py = h * 0.35 + ((i * 89 + Math.sin(t * 0.7 + i) * 20) % (h * 0.6))
      ctx.globalAlpha = 0.25 + 0.25 * Math.sin(t * 1.3 + i)
      ctx.beginPath()
      ctx.arc(px, py, 1.2, 0, Math.PI * 2)
      ctx.fill()
    }
    ctx.globalAlpha = 1

    // disturbance pulses on the meadow
    for (let i = pulses.length - 1; i >= 0; i--) {
      const age = t - pulses[i].born
      if (age > 2.4) {
        pulses.splice(i, 1)
        continue
      }
      const r = age * 220
      ctx.strokeStyle = `rgba(255,226,168,${0.45 * (1 - age / 2.4)})`
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.ellipse(pulses[i].x, pulses[i].y, r, r * 0.32, 0, 0, Math.PI * 2)
      ctx.stroke()
    }

    raf = requestAnimationFrame(draw)
  }
  raf = requestAnimationFrame(draw)

  return () => {
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
  }
}

import type { BedState } from '../prompts/types'

interface BedParams {
  hue: number
  state: BedState
}

/** Real open-world photography (public/scenes), shown when no Visko session is available. */
const SCENES = ['s1', 's2', 's3', 's4', 's5', 's6'].map((n) => `/scenes/${n}.jpg`)
const SCENE_SECONDS = 14
const FADE_SECONDS = 2.5

function coverDraw(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  w: number,
  h: number,
  zoom: number,
  panX: number,
  panY: number,
) {
  const scale = Math.max(w / img.width, h / img.height) * zoom
  const dw = img.width * scale
  const dh = img.height * scale
  const x = (w - dw) / 2 + panX * (dw - w) * 0.5
  const y = (h - dh) / 2 + panY * (dh - h) * 0.5
  ctx.drawImage(img, x, y, dw, dh)
}

/**
 * Offline stand-in for the Visko stream: a slow Ken-Burns slideshow of real
 * landscapes, warm-graded, still reacting to the prompt-program state machine.
 */
export function startProceduralBed(canvas: HTMLCanvasElement, getParams: () => BedParams) {
  const ctx = canvas.getContext('2d')!
  let raf = 0
  let t = 0
  const pulses: { x: number; y: number; born: number }[] = []
  let lastState: BedState = 'idle'

  const images: (HTMLImageElement | null)[] = SCENES.map(() => null)
  SCENES.forEach((src, i) => {
    const img = new Image()
    img.onload = () => {
      images[i] = img
    }
    img.src = src
  })

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = canvas.clientWidth * dpr
    canvas.height = canvas.clientHeight * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
  resize()
  window.addEventListener('resize', resize)

  const drawScene = (index: number, w: number, h: number, alpha: number, local: number) => {
    const img = images[index % images.length]
    if (!img) return
    ctx.save()
    ctx.globalAlpha = alpha
    const dir = index % 2 === 0 ? 1 : -1
    const zoom = 1.08 + local * 0.08
    coverDraw(ctx, img, w, h, zoom, dir * (local - 0.5) * 0.6, (local - 0.5) * 0.3 * dir)
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

    const base = ctx.createLinearGradient(0, 0, 0, h)
    base.addColorStop(0, '#3a3a46')
    base.addColorStop(0.5, '#a5704a')
    base.addColorStop(1, '#2a2a20')
    ctx.fillStyle = base
    ctx.fillRect(0, 0, w, h)

    const idx = Math.floor(t / SCENE_SECONDS)
    const local = (t % SCENE_SECONDS) / SCENE_SECONDS
    drawScene(idx, w, h, 1, local)
    const untilNext = SCENE_SECONDS - (t % SCENE_SECONDS)
    if (untilNext < FADE_SECONDS) {
      drawScene(idx + 1, w, h, 1 - untilNext / FADE_SECONDS, 0)
    }

    // warm golden-hour grade
    ctx.save()
    ctx.globalCompositeOperation = 'soft-light'
    ctx.fillStyle = 'rgba(255,190,120,0.35)'
    ctx.fillRect(0, 0, w, h)
    ctx.restore()

    // sun bloom, breathing with state
    const energy = state === 'replanning' ? 1 : state === 'drag' ? 0.8 : state === 'enter' ? 0.9 : 0.5
    const bloom = ctx.createRadialGradient(w * 0.7, h * 0.25, 0, w * 0.7, h * 0.25, w * 0.6)
    bloom.addColorStop(0, `rgba(255,220,170,${0.12 + 0.1 * energy * Math.sin(t * 0.8) ** 2})`)
    bloom.addColorStop(1, 'transparent')
    ctx.fillStyle = bloom
    ctx.fillRect(0, 0, w, h)

    // disturbance pulses
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

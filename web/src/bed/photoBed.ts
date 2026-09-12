import type { BedState } from '../prompts/types'

export interface PhotoBedParams {
  state: BedState
  hue: number
}

/** Ken-Burns the venue photo on a canvas and light it like an open-world scene. */
export function startPhotoBed(
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  getParams: () => PhotoBedParams,
): () => void {
  const ctx = canvas.getContext('2d')!
  let raf = 0
  let t = 0
  const pulses: { x: number; y: number; born: number }[] = []
  const dust = Array.from({ length: 40 }, () => ({
    x: Math.random(),
    y: Math.random(),
    speed: 0.008 + Math.random() * 0.012,
    phase: Math.random() * Math.PI * 2,
    size: 1 + Math.random(),
  }))
  let lastState: BedState = 'idle'

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = canvas.clientWidth * dpr
    canvas.height = canvas.clientHeight * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
  resize()
  window.addEventListener('resize', resize)

  const draw = () => {
    const { hue, state } = getParams()
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    t += 1 / 60

    if (state !== lastState) {
      if (state === 'drag' || state === 'alert') {
        pulses.push({
          x: w * (0.3 + Math.random() * 0.4),
          y: h * (0.5 + Math.random() * 0.3),
          born: t,
        })
      }
      lastState = state
    }

    const energy =
      state === 'replanning'
        ? 1
        : state === 'drag'
          ? 0.8
          : state === 'done'
            ? 0.65
            : state === 'enter'
              ? 0.9
              : 0.45

    const imageWidth = image.naturalWidth || image.width
    const imageHeight = image.naturalHeight || image.height
    const cover = Math.max(w / imageWidth, h / imageHeight)
    const scale = 1.08 + 0.04 * Math.sin(t * 0.07)
    const drawWidth = imageWidth * cover * scale
    const drawHeight = imageHeight * cover * scale
    const panX = Math.sin(t * 0.05) * w * 0.015
    const panY = Math.cos(t * 0.037) * h * 0.015

    ctx.globalCompositeOperation = 'source-over'
    ctx.drawImage(
      image,
      (w - drawWidth) / 2 + panX,
      (h - drawHeight) / 2 + panY,
      drawWidth,
      drawHeight,
    )

    ctx.globalCompositeOperation = 'multiply'
    ctx.fillStyle = `hsl(${hue} 45% ${78 - energy * 10}%)`
    ctx.globalAlpha = 0.35
    ctx.fillRect(0, 0, w, h)
    ctx.globalAlpha = 1

    ctx.globalCompositeOperation = 'screen'
    const sun = ctx.createRadialGradient(0, 0, 0, 0, 0, Math.max(w, h) * 0.9)
    sun.addColorStop(0, `rgba(242,198,109,${0.1 + energy * 0.08})`)
    sun.addColorStop(1, 'transparent')
    ctx.fillStyle = sun
    ctx.fillRect(0, 0, w, h)

    ctx.globalCompositeOperation = 'soft-light'
    const vignette = ctx.createRadialGradient(
      w / 2,
      h / 2,
      Math.min(w, h) * 0.15,
      w / 2,
      h / 2,
      Math.max(w, h) * 0.75,
    )
    vignette.addColorStop(0, 'transparent')
    vignette.addColorStop(1, 'rgba(20,17,13,0.6)')
    ctx.fillStyle = vignette
    ctx.fillRect(0, 0, w, h)
    ctx.globalCompositeOperation = 'source-over'

    for (const particle of dust) {
      const y = (((particle.y - t * particle.speed) % 1) + 1) % 1
      const x = (particle.x + Math.sin(t * 0.15 + particle.phase) * 0.005) * w
      ctx.fillStyle = 'rgba(242,198,109,0.35)'
      ctx.fillRect(x, y * h, particle.size, particle.size)
    }

    for (let i = pulses.length - 1; i >= 0; i--) {
      const age = t - pulses[i].born
      if (age > 1.6) {
        pulses.splice(i, 1)
        continue
      }
      const progress = age / 1.6
      ctx.strokeStyle = `rgba(255,154,77,${0.75 * (1 - progress)})`
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(pulses[i].x, pulses[i].y, Math.min(w, h) * 0.35 * progress, 0, Math.PI * 2)
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

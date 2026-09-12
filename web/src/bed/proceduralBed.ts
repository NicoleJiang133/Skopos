import type { BedState } from '../prompts/types'

interface BedParams {
  hue: number
  state: BedState
}

/**
 * Zero-dependency fallback world when no venue photo is loaded.
 */
export function startProceduralBed(canvas: HTMLCanvasElement, getParams: () => BedParams) {
  const ctx = canvas.getContext('2d')!
  let raf = 0
  let t = 0
  const pulses: { x: number; y: number; born: number }[] = []
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
    const accent = state === 'alert' ? 35 : state === 'done' || state === 'replanning' ? 95 : hue

    const sky = ctx.createLinearGradient(0, 0, 0, h)
    sky.addColorStop(0, '#14110d')
    sky.addColorStop(0.55, `hsl(${accent} 60% ${4 + energy * 4}%)`)
    sky.addColorStop(1, '#14110d')
    ctx.fillStyle = sky
    ctx.fillRect(0, 0, w, h)

    // perspective floor
    const horizon = h * 0.46
    ctx.save()
    ctx.strokeStyle = `hsla(${accent} 100% 65% / ${0.1 + energy * 0.16})`
    ctx.lineWidth = 1
    for (let i = -14; i <= 14; i++) {
      ctx.beginPath()
      ctx.moveTo(w / 2 + i * 18, horizon)
      ctx.lineTo(w / 2 + i * (w / 12), h)
      ctx.stroke()
    }
    for (let i = 1; i < 22; i++) {
      const p = i / 22
      const y = horizon + Math.pow(p, 2.4) * (h - horizon) + ((t * 26) % 30) * Math.pow(p, 2.4)
      if (y > h) continue
      ctx.globalAlpha = 0.14 + energy * 0.2 * p
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(w, y)
      ctx.stroke()
    }
    ctx.restore()

    // horizon bloom, breathing with state
    const bloom = ctx.createRadialGradient(w / 2, horizon, 0, w / 2, horizon, w * 0.55)
    const breathe = 0.35 + 0.25 * Math.sin(t * (state === 'replanning' ? 4.2 : 1.1))
    bloom.addColorStop(0, `hsla(${accent} 100% 62% / ${(0.2 + energy * 0.3) * breathe})`)
    bloom.addColorStop(1, 'transparent')
    ctx.fillStyle = bloom
    ctx.fillRect(0, 0, w, h)

    // scanning sweep while replanning
    if (state === 'replanning') {
      const sx = ((t * 0.45) % 1) * w
      const sweep = ctx.createLinearGradient(sx - 80, 0, sx + 80, 0)
      sweep.addColorStop(0, 'transparent')
      sweep.addColorStop(0.5, 'hsla(162 100% 60% / 0.22)')
      sweep.addColorStop(1, 'transparent')
      ctx.fillStyle = sweep
      ctx.fillRect(0, horizon, w, h - horizon)
    }

    // disturbance pulses
    for (let i = pulses.length - 1; i >= 0; i--) {
      const age = t - pulses[i].born
      if (age > 2.4) {
        pulses.splice(i, 1)
        continue
      }
      const r = age * 220
      ctx.strokeStyle = `hsla(${accent} 100% 70% / ${0.45 * (1 - age / 2.4)})`
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.ellipse(pulses[i].x, pulses[i].y, r, r * 0.32, 0, 0, Math.PI * 2)
      ctx.stroke()
    }

    // vignette keeps the center dark for the code layer
    const vig = ctx.createRadialGradient(w / 2, h / 2, h * 0.12, w / 2, h / 2, h * 0.95)
    vig.addColorStop(0, 'rgba(20,17,13,0.86)')
    vig.addColorStop(0.5, 'rgba(20,17,13,0.35)')
    vig.addColorStop(1, 'rgba(20,17,13,0.9)')
    ctx.fillStyle = vig
    ctx.fillRect(0, 0, w, h)

    raf = requestAnimationFrame(draw)
  }
  raf = requestAnimationFrame(draw)

  return () => {
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
  }
}

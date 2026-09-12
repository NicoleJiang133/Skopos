import { create } from 'zustand'
import { astar, type Cell } from '../planner/astar'
import type { BedState } from '../prompts/types'
import type { ScreenId } from '../prompts/screens'
import { INVENTORY, presetVenue, type ObjectType, type VenueGrid, type VenueObject } from './schema'

export interface Job {
  id: string
  kind: 'serve' | 'clean'
  label: string
  target: Cell
  status: 'queued' | 'active' | 'done'
}

export interface EventEntry {
  id: string
  at: number
  text: string
  tone: 'info' | 'action' | 'plan'
}

export interface Interaction {
  at: number
  screen: ScreenId
  kind: 'goto' | 'place' | 'move' | 'select_job' | 'photo' | 'drive'
  detail: Record<string, string | number>
}

interface State {
  screen: ScreenId
  bedState: BedState
  bedNudge: string | null
  live: boolean
  venuePhoto: Blob | null
  grid: VenueGrid
  robot: Cell
  heading: 0 | 1 | 2 | 3
  trail: Cell[]
  jobs: Job[]
  activeJobId: string
  route: Cell[]
  routeProgress: number
  events: EventEntry[]
  replanning: boolean
  interactions: Interaction[]

  goto: (screen: ScreenId) => void
  setBedState: (s: BedState) => void
  nudgeBed: (fragment: string, state?: BedState) => void
  setLive: (live: boolean) => void
  setVenuePhoto: (b: Blob | null) => void
  logInteraction: (kind: Interaction['kind'], detail: Interaction['detail']) => void
  exportInteractions: () => void
  addObject: (type: ObjectType, x: number, y: number) => void
  moveObject: (id: string, x: number, y: number) => void
  removeObject: (id: string) => void
  selectJob: (id: string) => void
  arrive: () => void
  driveRobot: (action: 'forward' | 'left' | 'right') => void
  replan: () => void
  pushEvent: (text: string, tone?: EventEntry['tone']) => void
}

let seq = 0
let moveTimer: number | undefined
const nextId = (p: string) => `${p}-${++seq}`

function occupied(grid: VenueGrid, ignoreId?: string) {
  const set = new Set<string>()
  for (const o of grid.objects) {
    if (o.id === ignoreId) continue
    for (let dx = 0; dx < o.w; dx++)
      for (let dy = 0; dy < o.h; dy++) set.add(`${o.x + dx},${o.y + dy}`)
  }
  return set
}

function uniqueObjectId(type: ObjectType, objects: VenueObject[]) {
  const used = new Set(objects.map((o) => o.id))
  let n = 1
  while (used.has(`${type}-${n}`)) n++
  return `${type}-${n}`
}

function planRoute(grid: VenueGrid, from: Cell, to: Cell): Cell[] {
  const blockedSet = occupied(grid)
  return astar(from, to, (c) => blockedSet.has(`${c.x},${c.y}`), grid.width, grid.height)
}

function defaultJobs(grid: VenueGrid): Job[] {
  const table2 = grid.objects.find((o) => o.id === 'table-2')!
  const zoneA = grid.zones.find((z) => z.id === 'zone-a')!
  return [
    {
      id: 'job-serve',
      kind: 'serve',
      label: 'Serve bar → Table 2',
      target: { x: table2.x, y: table2.y + table2.h },
      status: 'active',
    },
    {
      id: 'job-clean',
      kind: 'clean',
      label: 'Clean zone A',
      target: { x: zoneA.x + 1, y: zoneA.y + 1 },
      status: 'queued',
    },
  ]
}

const initialGrid = presetVenue()
const initialRobot: Cell = { x: 2, y: 12 }
const initialJobs = defaultJobs(initialGrid)

export const useStore = create<State>((set, get) => ({
  screen: 'landing',
  bedState: 'idle',
  bedNudge: null,
  live: true,
  venuePhoto: null,
  grid: initialGrid,
  robot: initialRobot,
  heading: 0,
  trail: [initialRobot],
  jobs: initialJobs,
  activeJobId: initialJobs[0].id,
  route: planRoute(initialGrid, initialRobot, initialJobs[0].target),
  routeProgress: 0,
  events: [
    { id: nextId('ev'), at: Date.now(), text: 'Venue preset loaded — WORLDS LONDON', tone: 'info' },
  ],
  replanning: false,
  interactions: [],

  goto: (screen) => {
    if (screen === 'live') set({ screen, bedState: 'enter', trail: [get().robot] })
    else set({ screen, bedState: 'enter' })
    get().logInteraction('goto', { to: screen })
    window.setTimeout(() => set({ bedState: 'idle' }), 1800)
  },

  setBedState: (bedState) => set({ bedState }),

  nudgeBed: (fragment, state = 'drag') => {
    set({ bedNudge: fragment, bedState: state })
  },

  setLive: (live) => set({ live }),

  setVenuePhoto: (venuePhoto) => {
    set({ venuePhoto })
    get().logInteraction('photo', { bytes: venuePhoto?.size ?? 0 })
  },

  logInteraction: (kind, detail) => {
    set((s) => ({
      interactions: [...s.interactions, { at: Date.now(), screen: s.screen, kind, detail }],
    }))
  },

  exportInteractions: () => {
    const payload = {
      exportedAt: new Date().toISOString(),
      venue: get().grid,
      interactions: get().interactions,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'skopos-ground-truth.json'
    link.click()
    URL.revokeObjectURL(url)
  },

  addObject: (type, x, y) => {
    const s = get()
    const item = INVENTORY.find((i) => i.type === type)!
    const clampedX = Math.max(0, Math.min(s.grid.width - item.w, x))
    const clampedY = Math.max(0, Math.min(s.grid.height - item.h, y))
    const blocked = occupied(s.grid)
    for (let dx = 0; dx < item.w; dx++)
      for (let dy = 0; dy < item.h; dy++)
        if (blocked.has(`${clampedX + dx},${clampedY + dy}`)) {
          get().pushEvent(`${item.label} — no room there`, 'info')
          return
        }
    const o: VenueObject = {
      id: uniqueObjectId(type, s.grid.objects),
      type,
      x: clampedX,
      y: clampedY,
      w: item.w,
      h: item.h,
      movable: item.movable,
      eventPrompt: item.eventPrompt,
      label: item.label,
    }
    set({ grid: { ...s.grid, objects: [...s.grid.objects, o] } })
    get().logInteraction('place', { type, x: clampedX, y: clampedY })
    get().pushEvent(`${item.label} placed at ${clampedX},${clampedY}`, 'action')
    get().nudgeBed(item.eventPrompt)
    get().replan()
  },

  moveObject: (id, x, y) => {
    const s = get()
    const target = s.grid.objects.find((o) => o.id === id)
    if (!target) return
    const clampedX = Math.max(0, Math.min(s.grid.width - target.w, x))
    const clampedY = Math.max(0, Math.min(s.grid.height - target.h, y))
    if (clampedX === target.x && clampedY === target.y) return
    const blocked = occupied(s.grid, id)
    for (let dx = 0; dx < target.w; dx++)
      for (let dy = 0; dy < target.h; dy++)
        if (blocked.has(`${clampedX + dx},${clampedY + dy}`)) return
    set({
      grid: {
        ...s.grid,
        objects: s.grid.objects.map((o) => (o.id === id ? { ...o, x: clampedX, y: clampedY } : o)),
      },
    })
    get().logInteraction('move', { id, x: clampedX, y: clampedY })
    get().pushEvent(`${target.label} moved → route replanned`, 'action')
    get().nudgeBed(target.eventPrompt)
    get().replan()
  },

  removeObject: (id) => {
    set((s) => ({ grid: { ...s.grid, objects: s.grid.objects.filter((o) => o.id !== id) } }))
    get().replan()
  },

  selectJob: (id) => {
    set((s) => ({
      activeJobId: id,
      jobs: s.jobs.map((j) => ({ ...j, status: j.id === id ? 'active' : 'queued' })),
    }))
    get().logInteraction('select_job', { id })
    get().replan()
  },

  arrive: () => {
    const s = get()
    const job = s.jobs.find((j) => j.id === s.activeJobId)
    if (!job || job.status === 'done') return
    set((st) => ({
      jobs: st.jobs.map((j) => (j.id === job.id ? { ...j, status: 'done' } : j)),
    }))
    get().pushEvent(`${job.label} — completed`, 'info')
    window.setTimeout(() => {
      const st = get()
      const nextJob = st.jobs.find((j) => j.status === 'queued')
      if (nextJob) return st.selectJob(nextJob.id)
      set({ jobs: st.jobs.map((j) => ({ ...j, status: 'queued' })) })
      st.pushEvent('Task cycle complete — requeueing', 'info')
      st.selectJob(st.jobs[0].id)
    }, 1400)
  },

  driveRobot: (action) => {
    const s = get()
    if (moveTimer) window.clearTimeout(moveTimer)

    if (action === 'left' || action === 'right') {
      const heading = ((s.heading + (action === 'left' ? 3 : 1)) % 4) as 0 | 1 | 2 | 3
      set({ heading })
      get().logInteraction('drive', { action, heading })
      get().nudgeBed(`the view turns ${action === 'left' ? 'left' : 'right'} smoothly`, 'move')
      moveTimer = window.setTimeout(() => set({ bedState: 'idle' }), 1200)
      return
    }

    const directions: Cell[] = [
      { x: 0, y: -1 },
      { x: 1, y: 0 },
      { x: 0, y: 1 },
      { x: -1, y: 0 },
    ]
    const direction = directions[s.heading]
    const next = { x: s.robot.x + direction.x, y: s.robot.y + direction.y }
    const blocked =
      next.x < 0 ||
      next.y < 0 ||
      next.x >= s.grid.width ||
      next.y >= s.grid.height ||
      occupied(s.grid).has(`${next.x},${next.y}`)

    if (blocked) {
      get().pushEvent('Blocked — something is in the way', 'info')
      set({ bedState: 'alert' })
      get().logInteraction('drive', { action, blocked: 1 })
      moveTimer = window.setTimeout(() => set({ bedState: 'idle' }), 900)
      return
    }

    const job = s.jobs.find((j) => j.id === s.activeJobId)
    const onRoute = s.route.some((c) => c.x === next.x && c.y === next.y) ? 1 : 0
    const route = job ? planRoute(s.grid, next, job.target) : []
    set({
      robot: next,
      trail: [...s.trail, next],
      route,
      routeProgress: 0,
      bedState: 'move',
    })
    get().logInteraction('drive', {
      action,
      x: next.x,
      y: next.y,
      heading: s.heading,
      onRoute,
    })
    moveTimer = window.setTimeout(() => set({ bedState: 'idle' }), 1200)
    if (job && next.x === job.target.x && next.y === job.target.y) get().arrive()
  },

  replan: () => {
    const s = get()
    const job = s.jobs.find((j) => j.id === s.activeJobId)
    if (!job) return
    set({ replanning: true, bedState: 'replanning' })
    window.setTimeout(() => {
      const cur = get()
      const route = planRoute(cur.grid, cur.robot, job.target)
      set({ route, routeProgress: 0, replanning: false, bedState: 'done' })
      cur.pushEvent(
        route.length > 0
          ? `Suggested route — ${route.length} cells to ${job.label}`
          : `No route to ${job.label} — floor blocked`,
        'plan',
      )
      window.setTimeout(() => set({ bedState: 'idle', bedNudge: null }), 2200)
    }, 650)
  },

  pushEvent: (text, tone = 'info') =>
    set((s) => ({
      events: [{ id: nextId('ev'), at: Date.now(), text, tone }, ...s.events].slice(0, 40),
    })),
}))

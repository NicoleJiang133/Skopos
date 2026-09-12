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
  kind: 'goto' | 'place' | 'move' | 'select_job' | 'photo'
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
  replan: () => void
  tickRobot: () => void
  pushEvent: (text: string, tone?: EventEntry['tone']) => void
}

let seq = 0
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
    set({ screen, bedState: 'enter' })
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
    const item = INVENTORY.find((i) => i.type === type)!
    const o: VenueObject = {
      id: nextId(type),
      type,
      x,
      y,
      w: item.w,
      h: item.h,
      movable: item.movable,
      eventPrompt: item.eventPrompt,
      label: item.label,
    }
    set((s) => ({ grid: { ...s.grid, objects: [...s.grid.objects, o] } }))
    get().logInteraction('place', { type, x, y })
    get().pushEvent(`${item.label} placed at ${x},${y}`, 'action')
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
          ? `Route replanned — ${route.length} cells to ${job.label}`
          : `No route to ${job.label} — floor blocked`,
        'plan',
      )
      window.setTimeout(() => set({ bedState: 'idle', bedNudge: null }), 2200)
    }, 650)
  },

  tickRobot: () => {
    const s = get()
    if (s.replanning || s.route.length < 2) return
    const next = Math.min(s.routeProgress + 1, s.route.length - 1)
    set({ routeProgress: next, robot: s.route[next] })
    if (next === s.route.length - 1) {
      const job = s.jobs.find((j) => j.id === s.activeJobId)
      if (job && job.status !== 'done') {
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
      }
    }
  },

  pushEvent: (text, tone = 'info') =>
    set((s) => ({
      events: [{ id: nextId('ev'), at: Date.now(), text, tone }, ...s.events].slice(0, 40),
    })),
}))

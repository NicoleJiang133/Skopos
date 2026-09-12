import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

/** Live Ops is first-person: the viewer IS the serving robot rolling through the venue. */
const states: Record<BedState, string> = {
  idle: 'First-person view from a small serving robot at knee height, standing still inside this venue: table legs and chair seats at eye level, warm sunlight on the floor, a calm room, very slow subtle sway.',
  enter:
    'First-person view from a small serving robot at knee height, the venue opening up ahead as the robot powers on, warm light settling over the floor.',
  move: 'First-person view from a small serving robot at knee height rolling smoothly forward through this venue, floor gliding underneath, table legs passing on both sides, steady handheld-free motion.',
  drag: 'First-person view from a small serving robot at knee height: a table nearby is being shifted, its shadow sliding across the floor, dust in the warm light.',
  replanning:
    'First-person view from a small serving robot at knee height, pausing and slowly turning to look for a new way between the tables.',
  done: 'First-person view from a small serving robot at knee height arriving beside a table and gently coming to rest, warm evening light.',
  alert:
    'First-person view from a small serving robot at knee height as the room dims and warm lanterns switch on over the tables.',
}

export const liveOpsProgram: PromptProgram = {
  anchor: '/keyframes/liveops.svg',
  fallback: '/fallback/liveops.mp4',
  hue: 90,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

const states: Record<BedState, string> = {
  idle: 'Top-down view of a holographic planning table in a dark room, faint volumetric grid light rising from its dark surface, slow rotating survey beam at the rim.',
  enter:
    'The planning table ignites: a volumetric projection unfolds upward from the dark table surface, edges tracing outward.',
  drag: 'The planning table surface ripples where an unseen object is being placed, concentric cyan interference rings spreading out from the center-left.',
  replanning:
    'Fine mint circuit light sweeps repeatedly across the table rim while the projection recalculates.',
  done: 'The projection settles into a calm steady state, soft mint confirmation glow fading at the rim.',
  alert: 'Amber warning light pulses along the table rim, haze tinted warm.',
}

export const setupProgram: PromptProgram = {
  anchor: '/keyframes/setup.svg',
  fallback: '/fallback/setup.mp4',
  hue: 168,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

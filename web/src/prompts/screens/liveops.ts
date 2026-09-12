import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

const states: Record<BedState, string> = {
  idle: 'First person view from inside a dark operations pod looking out over a hazy venue floor, HUD ambience light breathing slowly along the pod frame.',
  enter:
    'The pod canopy light ramps up as the venue floor resolves out of the haze ahead.',
  drag: 'A region of the venue floor ahead lights up and the haze disturbs there, light rippling outward from that zone.',
  replanning:
    'Mint light threads race across the venue floor as new paths are traced through the haze.',
  done: 'A single clean mint path glows across the venue floor, the pod frame settling back to calm cyan ambience.',
  alert:
    'Amber caution light floods the pod frame, the venue floor ahead tinted warm and hazy.',
}

export const liveOpsProgram: PromptProgram = {
  anchor: '/keyframes/liveops.svg',
  fallback: '/fallback/liveops.mp4',
  hue: 205,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

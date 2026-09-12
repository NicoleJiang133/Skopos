import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

const states: Record<BedState, string> = {
  idle: 'A sealed holographic operations bay door slowly warming up, dormant cyan seams breathing along its frame, dust motes drifting in the haze.',
  enter:
    'The bay door seams flare and the door begins to split open, cool light spilling forward into the dark deck, haze rolling toward camera.',
  drag: 'The bay door hangs half open, light shafts sweeping slowly across the deck floor.',
  replanning:
    'Cyan light travels in slow circuits around the door frame as unseen systems spin up.',
  done: 'The bay is fully open onto a dark deck, calm steady cyan ambience.',
  alert: 'Amber caution light washes the bay frame, the haze tinted warm.',
}

export const landingProgram: PromptProgram = {
  anchor: '/keyframes/landing.svg',
  fallback: '/fallback/landing.mp4',
  hue: 190,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

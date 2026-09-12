import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

const states: Record<BedState, string> = {
  idle: "High bird's-eye view looking down onto an empty stone courtyard of a countryside venue at golden hour, flagstone floor with warm sunlight, potted olive trees and ivy along the low walls, meadow and hills at the edges of frame.",
  enter:
    'The camera rises gently above the courtyard as the sun comes out and warm light spreads across the flagstones.',
  drag: 'Sunlight and canopy shadows shift across the courtyard floor as something is set down on the flagstones, a little dust catching the light.',
  replanning:
    'A soft breeze moves the ivy and canopy shadows across the courtyard while the light settles.',
  done: 'The courtyard rests still in warm evening light, long soft shadows across the stone.',
  alert: 'Clouds pass over the sun and warm lanterns glow along the courtyard walls.',
}

export const setupProgram: PromptProgram = {
  hue: 32,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

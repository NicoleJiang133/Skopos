import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

const states: Record<BedState, string> = {
  idle: 'Wide establishing shot of an open-air venue on a hillside at golden hour: a stone terrace with wooden tables, linen canopies swaying gently, rolling green fields and distant mountains beyond, birds drifting over the valley.',
  enter:
    'The camera drifts slowly forward through the terrace gate as sunlight breaks through the canopies and warm light spills across the stone floor.',
  drag: 'Sunlight shafts sweep slowly across the terrace floor as canopies move in a light breeze.',
  replanning:
    'Wind moves through the tall grass around the terrace in slow waves while the light softens.',
  done: 'The terrace rests in calm evening light, long soft shadows, still and welcoming.',
  alert: 'Warm lantern light comes on across the terrace as clouds pass over the sun.',
}

export const landingProgram: PromptProgram = {
  hue: 38,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

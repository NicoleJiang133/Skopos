import { composeWithBible } from '../styleBible'
import type { BedState, PromptProgram } from '../types'

const states: Record<BedState, string> = {
  idle: 'Low third-person view standing at the edge of a sunlit garden venue: wooden tables and chairs on grass and flagstones, a small serving robot resting by a stone bar, olive trees and a valley view beyond, golden hour.',
  enter:
    'The camera glides slowly into the garden venue as evening sunlight warms the tables and grass.',
  drag: 'A table in the garden is being carried to a new spot, its long shadow sliding across the grass, dust catching the low sun.',
  replanning:
    'The small robot pauses and turns, then rolls smoothly along a new winding path between the tables on the grass.',
  done: 'The robot arrives at a table and settles, the garden calm in warm evening light.',
  alert: 'The sky turns overcast and warm lanterns switch on across the garden tables.',
}

export const liveOpsProgram: PromptProgram = {
  hue: 90,
  states,
  composePrompt: (state) => composeWithBible(states[state]),
}

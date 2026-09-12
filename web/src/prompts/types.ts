export type BedState = 'idle' | 'enter' | 'drag' | 'replanning' | 'done' | 'alert'

export interface PromptProgram {
  /** procedural fallback bed hue, degrees */
  hue: number
  states: Record<BedState, string>
  composePrompt: (state: BedState) => string
}

export type BedState = 'idle' | 'enter' | 'drag' | 'replanning' | 'done' | 'alert'

export interface PromptProgram {
  /** image anchor used with set_image so composition never drifts */
  anchor: string
  /** looping fallback clip, one per screen */
  fallback: string
  /** procedural fallback bed hue, degrees */
  hue: number
  states: Record<BedState, string>
  composePrompt: (state: BedState) => string
}

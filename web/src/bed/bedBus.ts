import type { BedState } from '../prompts/types'

export type BedSourceKind = 'photo' | 'procedural'

export function debouncePrompt(fn: (prompt: string, state: BedState) => void) {
  let timer: number | undefined
  return (prompt: string, state: BedState) => {
    if (timer) window.clearTimeout(timer)
    timer = window.setTimeout(() => fn(prompt, state), 220)
  }
}

import type { PromptProgram } from '../types'
import { landingProgram } from './landing'
import { liveOpsProgram } from './liveops'
import { setupProgram } from './setup'

export type ScreenId = 'landing' | 'setup' | 'live'

export const programs: Record<ScreenId, PromptProgram> = {
  landing: landingProgram,
  setup: setupProgram,
  live: liveOpsProgram,
}

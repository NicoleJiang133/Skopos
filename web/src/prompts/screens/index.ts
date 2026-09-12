import type { PromptProgram } from '../types'
import type { ScreenId } from '../../state/schema'
import { landingProgram } from './landing'
import { liveOpsProgram } from './liveops'
import { setupProgram } from './setup'

export type { ScreenId } from '../../state/schema'

export const programs: Record<ScreenId, PromptProgram> = {
  landing: landingProgram,
  setup: setupProgram,
  live: liveOpsProgram,
  finish: liveOpsProgram,
}

import { composeWithBible } from './styleBible'
import type { BedState } from './types'
import type { ScreenId } from '../state/schema'

/**
 * Once the user has uploaded a photo of their physical venue, every screen is
 * rendered *inside that venue* — no preset terrace, courtyard or garden.
 * These prompts only ever describe camera, light and motion within the photo.
 */
const VENUE =
  'the exact venue shown in the provided photograph — same room, layout, furniture, materials and colours'

const scenes: Record<ScreenId, Record<BedState, string>> = {
  landing: {
    idle: `Wide establishing view of ${VENUE}, empty and quiet, warm afternoon light, very slow gentle camera drift.`,
    enter: `The camera eases forward into ${VENUE} as warm light settles across the floor.`,
    move: `The camera drifts slowly across ${VENUE}, light shifting softly on the surfaces.`,
    drag: `Inside ${VENUE}, a soft shadow slides across the floor, dust in the warm light.`,
    replanning: `Inside ${VENUE}, the camera pauses and turns slowly to take in the space.`,
    done: `Inside ${VENUE}, the room settles, calm and still in warm light.`,
    alert: `Inside ${VENUE}, the daylight dims and the venue's own lamps switch on.`,
  },
  setup: {
    idle: `High overhead view looking down onto the floor of ${VENUE}, steady, warm light, tables and counters seen from above.`,
    enter: `The overhead camera rises gently above the floor of ${VENUE}.`,
    move: `The overhead camera drifts slowly across the floor of ${VENUE}.`,
    drag: `From above, a piece of furniture in ${VENUE} is being shifted, its shadow sliding across the floor.`,
    replanning: `From above ${VENUE}, a thin path of light traces a new way between the furniture.`,
    done: `From above, ${VENUE} settles into its new arrangement, calm warm light.`,
    alert: `From above ${VENUE}, the light dims and the venue's lamps switch on.`,
  },
  live: {
    idle: `First-person view from a small serving robot at knee height, standing still inside ${VENUE}: table legs and chair seats at eye level, warm light on the floor, very slow subtle sway.`,
    enter: `First-person view from a small serving robot at knee height as ${VENUE} opens up ahead, warm light settling over the floor.`,
    move: `First-person view from a small serving robot at knee height rolling smoothly forward through ${VENUE}, floor gliding underneath, furniture passing on both sides, steady motion.`,
    drag: `First-person view from a small serving robot at knee height inside ${VENUE}: a nearby table is being shifted, its shadow sliding across the floor.`,
    replanning: `First-person view from a small serving robot at knee height inside ${VENUE}, pausing and slowly turning to look for a new way between the furniture.`,
    done: `First-person view from a small serving robot at knee height arriving beside a table in ${VENUE} and gently coming to rest.`,
    alert: `First-person view from a small serving robot at knee height inside ${VENUE} as the room dims and its lamps switch on.`,
  },
  play: {
    idle: `First-person view from a small serving robot at knee height, standing still inside ${VENUE}: table legs and chair seats at eye level, warm light on the floor, very slow subtle sway.`,
    enter: `First-person view from a small serving robot at knee height as ${VENUE} opens up ahead, warm light settling over the floor.`,
    move: `First-person view from a small serving robot at knee height rolling smoothly forward through ${VENUE}, floor gliding underneath, furniture passing on both sides, steady motion.`,
    drag: `First-person view from a small serving robot at knee height inside ${VENUE}: a nearby table is being shifted, its shadow sliding across the floor.`,
    replanning: `First-person view from a small serving robot at knee height inside ${VENUE}, pausing and slowly turning to look for a new way between the furniture.`,
    done: `First-person view from a small serving robot at knee height arriving beside a table in ${VENUE} and gently coming to rest.`,
    alert: `First-person view from a small serving robot at knee height inside ${VENUE} as the room dims and its lamps switch on.`,
  },
}

export const PHOTO_ANCHOR =
  'Stay strictly inside the provided photograph of this venue: keep its exact layout, architecture, furniture, materials and colours; never add rooms, outdoor scenery or furniture that is not in the photo; only change light, atmosphere and slow camera motion.'

export function composePhotoPrompt(screen: ScreenId, state: BedState): string {
  return `${composeWithBible(scenes[screen][state])} ${PHOTO_ANCHOR}`
}

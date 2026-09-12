import tokens from '../design/tokens.meta.json'

/**
 * Single source of truth for generative-side consistency.
 * Every screen prompt inherits this prefix, so the whole product reads as
 * one game engine output rather than a set of unrelated shots.
 */
const palette = Object.values(tokens.palette)
  .map((c) => `${c.prompt} ${c.hex}`)
  .join(', ')

export const STYLE_BIBLE = [
  `Cinematic real-time 3D game render, ${tokens.era}.`,
  `Palette: ${palette}.`,
  `Materials: ${tokens.materials.join('; ')}.`,
  `Lighting: ${tokens.lighting.join('; ')}.`,
  `Camera: ${tokens.camera.join('; ')}.`,
  'Absolutely no readable text, no logos, no user interface widgets, no people in frame.',
  'The central third of the frame stays dark and low-detail.',
].join(' ')

export const NEGATIVE = [
  'text',
  'letters',
  'watermark',
  'ui overlay',
  'buttons',
  'charts',
  'fast cuts',
  'camera shake',
  'oversaturation',
].join(', ')

export function composeWithBible(body: string): string {
  return `${STYLE_BIBLE} ${body} Avoid: ${NEGATIVE}.`
}

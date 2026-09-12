/** Grid JSON schema — the contract shared with the robotics side. */
export const GRID_SCHEMA_VERSION = 1

export type ScreenId = 'landing' | 'setup' | 'live' | 'play'

export type ObjectType = 'bar' | 'table' | 'chair' | 'plant' | 'stage' | 'dock'

export interface VenueObject {
  id: string
  type: ObjectType
  /** top-left cell */
  x: number
  y: number
  /** footprint in cells */
  w: number
  h: number
  movable: boolean
  /** appended to the bed prompt when this object is disturbed */
  eventPrompt: string
  label: string
}

export interface Zone {
  id: string
  kind: 'cleaning' | 'serving'
  x: number
  y: number
  w: number
  h: number
  label: string
}

export interface VenueGrid {
  version: number
  name: string
  width: number
  height: number
  objects: VenueObject[]
  zones: Zone[]
}

export interface InventoryItem {
  type: ObjectType
  label: string
  w: number
  h: number
  movable: boolean
  eventPrompt: string
}

export const INVENTORY: InventoryItem[] = [
  {
    type: 'bar',
    label: 'Bar',
    w: 4,
    h: 1,
    movable: false,
    eventPrompt: 'a long service counter re-forms along one edge of the floor',
  },
  {
    type: 'table',
    label: 'Table',
    w: 2,
    h: 2,
    movable: true,
    eventPrompt: 'a round table footprint shifts across the floor, light rippling under it',
  },
  {
    type: 'chair',
    label: 'Chair',
    w: 1,
    h: 1,
    movable: true,
    eventPrompt: 'small seat markers scatter and resettle',
  },
  {
    type: 'plant',
    label: 'Plant',
    w: 1,
    h: 1,
    movable: true,
    eventPrompt: 'a tall planter silhouette casts a soft shadow across the floor',
  },
  {
    type: 'stage',
    label: 'Stage',
    w: 5,
    h: 3,
    movable: false,
    eventPrompt: 'a raised platform glows at the far end of the floor',
  },
  {
    type: 'dock',
    label: 'Dock',
    w: 2,
    h: 1,
    movable: false,
    eventPrompt: 'a charging berth pulses in the corner of the floor',
  },
]

/** Preset that matches tonight's venue, so the demo needs zero typing. */
export function presetVenue(): VenueGrid {
  return {
    version: GRID_SCHEMA_VERSION,
    name: 'WORLDS LONDON — main floor',
    width: 20,
    height: 14,
    objects: [
      obj('bar-1', 'bar', 1, 1),
      obj('stage-1', 'stage', 13, 1),
      obj('table-1', 'table', 5, 5),
      obj('table-2', 'table', 10, 6),
      obj('table-3', 'table', 6, 10),
      obj('plant-1', 'plant', 3, 11),
      obj('plant-2', 'plant', 17, 11),
      obj('dock-1', 'dock', 1, 12),
    ],
    zones: [
      { id: 'zone-a', kind: 'cleaning', x: 14, y: 8, w: 5, h: 4, label: 'Cleaning zone A' },
      { id: 'zone-b', kind: 'serving', x: 9, y: 5, w: 4, h: 4, label: 'Serving area' },
    ],
  }
}

function obj(id: string, type: ObjectType, x: number, y: number): VenueObject {
  const item = INVENTORY.find((i) => i.type === type)!
  return {
    id,
    type,
    x,
    y,
    w: item.w,
    h: item.h,
    movable: item.movable,
    eventPrompt: item.eventPrompt,
    label: `${item.label} ${id.split('-')[1]}`,
  }
}

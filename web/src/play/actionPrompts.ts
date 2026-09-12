/**
 * Action prompts attached to objects the robot reaches in the venue.
 *
 * Each prompt is written in the robot's first person ("You reach …") and offers
 * 3–4 choices. Every choice maps to one of the backend bandit strategies so the
 * user's clicks become ground truth for how they want the robot to behave:
 *   direct   → direct_approach
 *   careful  → slow_scan_then_approach
 *   arc      → wide_arc
 *   ask      → request_human_assist
 *   skip     → leave it / do nothing (not a backend strategy; logged as preference)
 */

export type Strategy = 'direct' | 'careful' | 'arc' | 'ask' | 'skip'

export interface ActionChoice {
  id: string
  /** Imperative verb phrase on the button, e.g. "Lift the box". */
  label: string
  /** One-line consequence hint under the label. */
  hint: string
  strategy: Strategy
}

export interface ActionPrompt {
  /** First-person situation, e.g. "You reach the coffee table. A box sits on it." */
  situation: string
  /** The question the robot asks itself. */
  question: string
  choices: ActionChoice[]
}

export interface SceneObjectLite {
  id: string
  label: string
  material?: string
  hazards?: string[]
  confidence?: number
}

const ask = (label: string): ActionChoice => ({
  id: 'ask',
  label: 'Ask a human',
  hint: `Ping staff about the ${label} and wait`,
  strategy: 'ask',
})
const skip = (what = 'Leave it'): ActionChoice => ({
  id: 'skip',
  label: what,
  hint: 'Move on to the next thing',
  strategy: 'skip',
})

/** Prompts keyed by object label (lower-case, substring match). */
const BY_LABEL: [RegExp, (o: SceneObjectLite) => ActionPrompt][] = [
  [
    /table|desk|counter|bar/,
    (o) => ({
      situation: `You reach the ${o.label}. A box sits on top of it.`,
      question: 'What do you do?',
      choices: [
        { id: 'lift', label: 'Lift the box', hint: 'Grip both sides and carry it to the dock', strategy: 'direct' },
        { id: 'slide', label: 'Slide it to the edge first', hint: 'Test the weight before committing', strategy: 'careful' },
        { id: 'around', label: 'Go around the table', hint: 'Keep clear and come back later', strategy: 'arc' },
        ask(o.label),
      ],
    }),
  ],
  [
    /mug|cup|glass\b|bottle|vase/,
    (o) => ({
      situation: `A ${o.label} is within reach — ${o.material ?? 'fragile'}, half full.`,
      question: 'How do you handle it?',
      choices: [
        { id: 'grab', label: 'Pick it up', hint: 'Straight grip, normal speed', strategy: 'direct' },
        { id: 'gentle', label: 'Pick it up slowly', hint: 'Half speed, two-finger grip, check for liquid', strategy: 'careful' },
        { id: 'leave', label: 'Leave it', hint: "Not yours to move — someone may still be using it", strategy: 'skip' },
        ask(o.label),
      ],
    }),
  ],
  [
    /sofa|couch|chair|bench|stool/,
    (o) => ({
      situation: `Someone left a jacket on the ${o.label}.`,
      question: 'Do you tidy it?',
      choices: [
        { id: 'fold', label: 'Fold it and set it aside', hint: 'Neat pile on the seat', strategy: 'direct' },
        { id: 'leave', label: 'Leave personal items alone', hint: 'Never touch guests’ belongings', strategy: 'skip' },
        ask(o.label),
      ],
    }),
  ],
  [
    /rug|carpet|mat/,
    (o) => ({
      situation: `The ${o.label} edge is curled up across your path.`,
      question: 'How do you cross?',
      choices: [
        { id: 'over', label: 'Drive straight over it', hint: 'Fastest; small bump', strategy: 'direct' },
        { id: 'slow', label: 'Slow down and cross', hint: 'Lift the wheels gently at the edge', strategy: 'careful' },
        { id: 'around', label: 'Go around the rug', hint: 'Longer route, no risk', strategy: 'arc' },
        { id: 'flatten', label: 'Flatten the edge first', hint: 'Fix the hazard for everyone', strategy: 'careful' },
      ],
    }),
  ],
  [
    /cable|cord|wire/,
    (o) => ({
      situation: `A ${o.label} runs loose across the floor ahead.`,
      question: 'What do you do?',
      choices: [
        { id: 'step', label: 'Roll over it', hint: 'Quick, might tug on whatever it powers', strategy: 'direct' },
        { id: 'around', label: 'Route around it', hint: 'Add a few seconds, zero contact', strategy: 'arc' },
        { id: 'report', label: 'Report the hazard', hint: 'Flag it and let staff fix it', strategy: 'ask' },
        skip('Wait for it to clear'),
      ],
    }),
  ],
  [
    /door|window|mirror|screen/,
    (o) => ({
      situation: `You reach the ${o.label}. It's reflective — your depth sensor is unsure.`,
      question: 'How do you proceed?',
      choices: [
        { id: 'through', label: 'Push through', hint: 'Trust the map, ignore the sensor', strategy: 'direct' },
        { id: 'scan', label: 'Stop and re-scan', hint: 'Take a second look before moving', strategy: 'careful' },
        { id: 'wait', label: 'Wait for someone to open it', hint: 'Hold position by the door', strategy: 'ask' },
        { id: 'back', label: 'Turn back', hint: 'Find another way', strategy: 'arc' },
      ],
    }),
  ],
  [
    /plant|pot|lamp|sculpture|decor/,
    (o) => ({
      situation: `A ${o.label} (${o.material ?? 'fragile'}) is right on the corner you need to pass.`,
      question: 'Which way?',
      choices: [
        { id: 'squeeze', label: 'Squeeze past', hint: 'Tight but quick', strategy: 'direct' },
        { id: 'wide', label: 'Give it a wide berth', hint: 'Swing out into the aisle', strategy: 'arc' },
        { id: 'nudge', label: 'Nudge it aside', hint: 'Move it 20 cm out of the way', strategy: 'careful' },
        skip(),
      ],
    }),
  ],
  [
    /bowl|spill|puddle|liquid|drink/,
    (o) => ({
      situation: `There's a ${o.label} on the floor — liquid, easy to knock.`,
      question: 'What do you do?',
      choices: [
        { id: 'around', label: 'Steer clear', hint: 'Wide arc, no contact', strategy: 'arc' },
        { id: 'move', label: 'Move it to the wall', hint: 'Carefully, both hands', strategy: 'careful' },
        { id: 'report', label: 'Report it', hint: 'Let staff decide', strategy: 'ask' },
      ],
    }),
  ],
  [
    /cat|dog|pet|person|guest|child|kid/,
    (o) => ({
      situation: `A ${o.label} is in your path and moving.`,
      question: 'How do you react?',
      choices: [
        { id: 'stop', label: 'Stop and wait', hint: 'Stay still until the path clears', strategy: 'careful' },
        { id: 'around', label: 'Go around', hint: 'Slow curve, keep 1 m distance', strategy: 'arc' },
        { id: 'through', label: 'Keep going', hint: 'They will move', strategy: 'direct' },
        { id: 'speak', label: 'Announce yourself', hint: '“Excuse me, coming through”', strategy: 'ask' },
      ],
    }),
  ],
  [
    /box|crate|package|bag|tray/,
    (o) => ({
      situation: `A ${o.label} blocks the aisle. It looks heavy.`,
      question: 'What do you do?',
      choices: [
        { id: 'lift', label: 'Lift it', hint: 'Carry it to the storage area', strategy: 'direct' },
        { id: 'push', label: 'Push it aside', hint: 'Slide it flush against the wall', strategy: 'careful' },
        { id: 'around', label: 'Go around', hint: 'Not your job', strategy: 'arc' },
        ask(o.label),
      ],
    }),
  ],
]

/** Hazard-driven fallback when the label doesn't match a scripted situation. */
const BY_HAZARD: Record<string, (o: SceneObjectLite) => ActionPrompt> = {
  fragile: (o) => ({
    situation: `You reach the ${o.label}. It's fragile.`,
    question: 'Touch it?',
    choices: [
      { id: 'handle', label: 'Handle it normally', hint: 'It will probably be fine', strategy: 'direct' },
      { id: 'gentle', label: 'Handle it gently', hint: 'Half speed, soft grip', strategy: 'careful' },
      skip(),
    ],
  }),
  trip: (o) => ({
    situation: `The ${o.label} is a trip hazard on your route.`,
    question: 'Cross or avoid?',
    choices: [
      { id: 'cross', label: 'Cross it', hint: 'Quick and direct', strategy: 'direct' },
      { id: 'around', label: 'Avoid it', hint: 'Detour around', strategy: 'arc' },
      { id: 'report', label: 'Report it', hint: 'Flag for staff', strategy: 'ask' },
    ],
  }),
  moving: (o) => ({
    situation: `The ${o.label} is moving near you.`,
    question: 'How do you react?',
    choices: [
      { id: 'stop', label: 'Stop and wait', hint: 'Let it pass', strategy: 'careful' },
      { id: 'around', label: 'Go around', hint: 'Keep your distance', strategy: 'arc' },
      { id: 'through', label: 'Keep going', hint: 'Hold your course', strategy: 'direct' },
    ],
  }),
  reflective: (o) => ({
    situation: `The ${o.label} reflects light — your sensors disagree.`,
    question: 'Trust the map or the eyes?',
    choices: [
      { id: 'map', label: 'Trust the map', hint: 'Keep moving', strategy: 'direct' },
      { id: 'rescan', label: 'Stop and re-scan', hint: 'Take a second look', strategy: 'careful' },
      ask(o.label),
    ],
  }),
  spill: (o) => ({
    situation: `Liquid near the ${o.label}.`,
    question: 'What do you do?',
    choices: [
      { id: 'around', label: 'Steer clear', hint: 'Wide arc', strategy: 'arc' },
      { id: 'report', label: 'Report the spill', hint: 'Someone should mop', strategy: 'ask' },
      { id: 'through', label: 'Drive through', hint: 'Wheels can take it', strategy: 'direct' },
    ],
  }),
}

const GENERIC = (o: SceneObjectLite): ActionPrompt => ({
  situation: `You reach the ${o.label}.`,
  question: 'What do you do here?',
  choices: [
    { id: 'inspect', label: 'Take a closer look', hint: 'Stop and scan for 2 seconds', strategy: 'careful' },
    { id: 'pass', label: 'Pass by', hint: 'Nothing to do here', strategy: 'skip' },
    ask(o.label),
  ],
})

export function promptFor(o: SceneObjectLite): ActionPrompt {
  const label = o.label.toLowerCase()
  const scripted = BY_LABEL.find(([re]) => re.test(label))
  if (scripted) return scripted[1](o)
  const hazard = (o.hazards ?? []).find((h) => h in BY_HAZARD)
  if (hazard) return BY_HAZARD[hazard](o)
  return GENERIC(o)
}

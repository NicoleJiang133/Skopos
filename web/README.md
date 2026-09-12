# Skopos — Generative UI Shell

Venue-ops product for cleaning + serving robots. The uploaded venue photo becomes the
living world behind every screen, with a procedural fallback when no photo is loaded.
The interactive layer (React) floats on top sharing the same design tokens. Screens morph,
never hard-cut.

## Run

```
cd web && npm i
npm run dev
```

The bed renders the venue photo with a slow living-world treatment (`bed: photo`) and uses the
procedural canvas as a no-photo fallback (`bed: procedural`). Prompt programs provide the
descriptive world note and procedural hue for each screen.

## Layout

- `src/design/tokens.css` + `tokens.meta.json` — code-layer tokens, also feed the style bible
- `src/prompts/styleBible.ts` — shared prompt prefix; `src/prompts/screens/*` — per-screen programs
- `src/bed/` — GenerativeBed (venue photo world, procedural fallback, world-state bus)
- venue photo → living world; interactions logged and exportable as ground-truth JSON
- `src/floor/` — grid editor + inventory; `src/hud/` — tasks, event feed
- `src/planner/astar.ts` — local replanning; `src/state/schema.ts` — grid JSON contract
- `public/keyframes/` — image references

## Verify

`npx tsc -b && npx vite build`

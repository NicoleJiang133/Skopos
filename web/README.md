# Skopos — Generative UI Shell (Reactor / Visko Orbis Stable)

Venue-ops product for cleaning + serving robots. One persistent Visko session is the
"game world" behind every screen; the interactive layer (React) floats on top sharing the
same design tokens. Screens morph, never hard-cut.

## Run

```
cd web && npm install
REACTOR_API_KEY=rk_... node server/token.mjs   # token server, port 8787 (key never reaches the browser)
npm run dev                                    # http://localhost:5173, proxies /api -> :8787
```

The browser mints a short-lived JWT from `/api/token`, connects `ViskoOrbisStableModel`, and streams
`main_video` into the bed (`bed: live` badge, bottom-left). The account allows one concurrent Visko
session, so the page releases its session on unload (`/api/session/:id` beacon) and on reconnect.
Without a key, or if the stream fails, the bed falls back to a procedural world driven by the same
prompt-program state machine (`bed: procedural`).

## Layout

- `src/design/tokens.css` + `tokens.meta.json` — code-layer tokens, also feed the style bible
- `src/prompts/styleBible.ts` — shared prompt prefix; `src/prompts/screens/*` — per-screen programs
- `src/bed/` — GenerativeBed (Visko session, set_prompt/set_image bus, fallback)
- venue photo → Visko image anchor (uploadFile + setImage) with a local canvas fallback; interactions logged and exportable as ground-truth JSON
- Landing (photo required) → Setup → Live (first-person: drive the robot with arrows/WASD; A* is only a suggested route; deviations are logged)
- `src/floor/` — grid editor + inventory; `src/hud/` — tasks, event feed
- `src/planner/astar.ts` — local replanning; `src/state/schema.ts` — grid JSON contract
- `public/keyframes/` — image anchors; `public/fallback/` — pre-recorded loops
- `server/token.mjs` — rk_ → JWT exchange

## Verify

`npx tsc -b && npx vite build`

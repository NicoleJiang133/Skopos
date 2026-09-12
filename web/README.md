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

## Backend handoff

When a venue photo is submitted, Landing posts it to the game backend and then opens the backend
page. Set `VITE_BACKEND_URL` to override the handoff URL and `VITE_BACKEND_SCAN_BASE` to override
the scan API base. In development, scans use the `/backend` Vite proxy to
`http://127.0.0.1:8000`.

```sh
git clone -b local-build https://github.com/msimakhov-star/Skopos.git
cd Skopos
./run.sh
```

The backend requirements pin `onnxruntime==1.30.0`, which does not exist on PyPI for Python 3.10;
the local setup installs it unpinned.

## Layout

- `src/design/tokens.css` + `tokens.meta.json` — code-layer tokens, also feed the style bible
- `src/prompts/styleBible.ts` — shared prompt prefix; `src/prompts/screens/*` — per-screen programs
- `src/bed/` — GenerativeBed (Visko session, set_prompt/set_image bus, fallback)
- venue photo → Visko image anchor (uploadFile + setImage) with a local canvas fallback; interactions logged and exportable as ground-truth JSON
- Landing (photo required) → Setup → Live (first-person: drive the robot with arrows/WASD; A* is only a suggested route; deviations are logged)
- With a photo set, the grid starts empty and every Visko prompt is confined to that venue (`prompts/photoWorld.ts`); jobs are derived from the tables you place.
- `src/floor/` — grid editor + inventory; `src/hud/` — tasks, event feed
- `src/planner/astar.ts` — local replanning; `src/state/schema.ts` — grid JSON contract
- `public/keyframes/` — image anchors; `public/fallback/` — pre-recorded loops
- `server/token.mjs` — rk_ → JWT exchange

## Verify

`npx tsc -b && npx vite build`

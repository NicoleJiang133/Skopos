# Provider swap — mock to live in under ten minutes

Skopos ships on a mock provider so it runs with no keys and no network. This is
the checklist to point it at a real world model. Every step is a thing to *do*
and a thing to *check*.

The interface you are satisfying is `providers/base.py`:

```python
class WorldModelProvider:
    name: str
    live: bool
    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame: ...
    def health(self) -> dict: ...
```

`Frame.data_url` must be something an `<img>` can display — `data:image/png;base64,…`
is what the UI expects from a raster provider.

## The budget rule — read this before you wire anything up

**Only `campaign.elite(12)` is ever rendered.** A campaign scores 20,000
configurations on the scene graph via `engine.surrogate`; twelve of them get a
world-model call. That ratio is the entire reason the surrogate exists, and
`app.py` has no code path that renders a whole campaign. Do not add one. If you
raise `ELITE_K`, you are multiplying your provider bill by the same factor.

---

## Reactor (reactor.inc) — the headline path

The adapter in `providers/reactor.py` was written against the public docs at
<https://docs.reactor.inc>, read at build time (12 Sept 2026). It has **not**
been executed against the live API — we had no key. Facts taken from the docs
are marked `[docs]` in the source; our inferences are marked `TODO(reactor)`.

### 0. Before you start (1 min)

```bash
pip install reactor-sdk pillow          # pillow is NOT in requirements.txt
cp .env.example .env
```

Pillow is needed only to encode the SDK's numpy frames to PNG. If you would
rather not add it, switch the UI to a binary WebSocket frame channel instead.

### 1. Credentials (1 min)

In `.env`:

```
SKOPOS_PROVIDER=reactor
REACTOR_API_KEY=rk_...
REACTOR_MODEL=reactor/helios
SKOPOS_REFERENCE=rendered
```

`SKOPOS_REFERENCE=rendered` is the default and keeps the privacy claim intact:
the reference is drawn from the scene graph, not photographed. Setting it to
`photo` uploads real pixels and changes what the UI is allowed to claim.

- [ ] **Confirm the model slug.** `reactor/helios` is the example in the docs.
      Do not guess an alternative — ask, or read the model list.
- [ ] **Confirm the auth path.** The Python SDK is documented as exchanging the
      `rk_...` key for a JWT internally. If your account requires a server-side
      mint, that is `POST https://api.reactor.inc/tokens`; pass the resulting
      JWT instead of the raw key.

### 2. Resolve the open TODOs (5 min)

All are marked `TODO(reactor)` in `providers/reactor.py`.

- [ ] **The output handle.** The docs show `@output.on_frame` but not where
      `output` comes from. Find it (an attribute on `Reactor`? an awaited call?
      a `trackReceived` event carrying the `"main_video"` track?) and replace
      `output = getattr(reactor, "output", None)`.
- [ ] **Mid-stream prompt updates.** We assume a second
      `send_command("set_prompt", …)` re-steers a live session. Confirm, and
      confirm the stop command.
- [ ] **The event loop.** `_reactor_loop()` reaches for `reactor._loop` so it
      can schedule commands from the render thread. Replace with whatever the
      SDK exposes publicly.
- [ ] **Conditioning.** This is now wired: `SKOPOS_REFERENCE=rendered` (the
      default) draws a layout reference from the scene graph and uploads it with
      `upload_file()` → `FileRef` → `send_command(IMAGE_COMMAND, ...)`. Confirm
      from the schema that your model's image command and field are really
      `set_image` / `image`, and override `REACTOR_IMAGE_COMMAND` /
      `REACTOR_IMAGE_FIELD` if not. Probe it first with
      `--reference` to see the upload accepted before trusting the app path.

### 3. Run it (1 min)

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8077
```

- [ ] Startup log shows `provider=reactor`.
- [ ] `curl -s localhost:8077/api/health` shows `"status": "streaming"` and
      `"live": true`.
- [ ] The UI provider badge reads **`reactor · live`** and turns green. If it
      reads `reactor(fallback:mock)`, the frame's `meta.reason` says why.

### 4. Check the honesty surface (2 min)

- [ ] The badge must never say `live` while mock frames are on screen. The
      fallback path sets `meta.live = false` — keep it that way.
- [ ] Update README limitation 5, which currently says the adapter has never
      been run live. Once it has, say so, and say what you verified.
- [ ] Re-run `python selftest.py`. The mock-provider check must still pass: the
      zero-key path is non-negotiable and must not rot.

### Failure modes, in the order you will hit them

| symptom | cause |
| --- | --- |
| badge stuck on `reactor(fallback:mock)` | no key, SDK not installed, or the background thread raised — read `health().status` |
| frames arrive then stop | the staleness cut-off in `render()` is 2 s; check the socket, then raise it |
| `Pillow is not installed` in the log | `pip install pillow` |
| `TODO(reactor): could not find the frame output handle` | item 1 above, unresolved |
| provider bill higher than expected | someone raised `ELITE_K` in `app.py` |

---

## Runware (fallback)

`providers/runware.py` is a stub with the same interface, never run against the
live API. It is a per-image API rather than a real-time stream, which suits
Skopos fine: we render twelve stills per campaign, not a video. Open items are
marked `TODO(runware)`.

---

## Writing a new provider

1. Subclass `WorldModelProvider` in `providers/yours.py`.
2. Return a `Frame` whose `data_url` an `<img>` can render.
3. Register it in `build_provider()` in `app.py`.
4. Set `live = True` **only** when real frames are actually flowing, and fall
   back to `MockProvider` rather than to a blank screen — with
   `meta["live"] = False` and a `meta["reason"]`, so the UI can tell the truth
   about what is on screen.

# Provider swap — mock to live in under ten minutes

Skopos ships on a mock provider so it runs with no keys and no network. This is
the checklist to point it at a real world model. Every step is a thing to *do*
and a thing to *check*.

The interface you are satisfying is `skopos/providers/base.py`:

```python
class WorldModelProvider:
    name: str
    live: bool
    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame: ...
    def health(self) -> dict: ...
```

`Frame.data_url` must be something an `<img>` can display — `data:image/png;base64,…`
is what the UI expects from a raster provider.

---

## Reactor (reactor.inc) — the headline path

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
```

- [ ] **Confirm the model slug.** `reactor/helios` is the example in the docs.
      Do not guess an alternative — ask, or read the model list.
- [ ] **Confirm the auth path.** The Python SDK is documented as exchanging the
      `rk_...` key for a JWT internally. If your account requires a server-side
      mint, that is `POST https://api.reactor.inc/tokens`; pass the resulting JWT
      instead of the raw key.

### 2. Resolve the four open TODOs (5 min)

All of them are marked `TODO(reactor)` in `skopos/providers/reactor.py`.

- [ ] **TODO(reactor) 3 — the output handle.** The docs show
      `@output.on_frame`, but not where `output` comes from. Find it (an
      attribute on `Reactor`? an awaited call? a `trackReceived` event carrying
      the `"main_video"` track?) and replace
      `output = getattr(reactor, "output", None)`.
- [ ] **TODO(reactor) 5 — mid-stream prompt updates.** We assume a second
      `send_command("set_prompt", …)` re-steers a live session. Confirm, and
      confirm the stop command.
- [ ] **The event loop.** `_reactor_loop()` currently reaches for
      `reactor._loop` so it can schedule commands from the render thread.
      Replace with whatever the SDK exposes publicly.
- [ ] **TODO(reactor) 4 — conditioning.** This is the one that matters for
      quality. We currently drive the model **prompt-only**, which throws away
      the layout we spent perception extracting. If Reactor supports image or
      video conditioning, feed it the mock provider's SVG rendered to PNG as a
      layout hint. Until then, say "prompt-conditioned" out loud; do not imply
      the render is faithful to the SceneGraph.

### 3. Run it (1 min)

```bash
python -m uvicorn skopos.server:app --host 127.0.0.1 --port 8077
```

- [ ] Startup log shows `provider=reactor`.
- [ ] `curl -s localhost:8077/api/health | python -m json.tool` shows
      `"status": "streaming"` and `"live": true`.
- [ ] The UI provider badge reads **`reactor · live`** and turns green. If it
      reads `reactor(fallback:mock)`, the `meta.reason` field on the frame says
      exactly why.

### 4. Check the honesty surface (2 min)

- [ ] The provider badge must never say `live` while mock frames are on screen.
      The fallback path sets `meta.live = false` — keep it that way.
- [ ] Update README limitation #5. It currently says the adapter has never been
      run against the live API. Once it has, say so, and say what you verified.
- [ ] Re-run `python -m skopos.selftest`. The mock-provider check must still
      pass: the zero-key path is non-negotiable and must not rot.

### Failure modes, in the order you will hit them

| symptom | cause |
| --- | --- |
| badge stuck on `reactor(fallback:mock)` | no key, SDK not installed, or the background thread raised — read `health().status` |
| frames arrive then stop | our staleness cut-off is 2 s; check the socket, then raise it in `render()` |
| `Pillow is not installed` in the log | `pip install pillow` |
| `TODO(reactor): could not find the frame output handle` | item 3 above, unresolved |

---

## Runware (fallback)

`skopos/providers/runware.py` is a stub with the same interface. It is a
per-image API, not a real-time stream, so before wiring it decide whether to
render **one frame per attempt** rather than one per step — otherwise the loop
will be dominated by image latency. Open items are marked `TODO(runware)`.

---

## Writing a new provider

1. Subclass `WorldModelProvider` in `skopos/providers/yours.py`.
2. Return a `Frame` whose `data_url` an `<img>` can render.
3. Register it in `build_provider()` in `skopos/server.py`.
4. Set `live = True` **only** when real frames are actually flowing, and fall
   back to `MockProvider` rather than to a blank screen — with
   `meta["live"] = False` and a `meta["reason"]`, so the UI can tell the truth
   about what is on screen.

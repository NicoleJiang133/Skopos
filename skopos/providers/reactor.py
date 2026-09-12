"""
Reactor (reactor.inc) world-model provider.

STATUS: adapter written against the public docs at https://docs.reactor.inc,
read at build time (12 Sept 2026). It has NOT been executed against the live
API — we had no key in the room. Everything below that came from the docs is
marked [docs]; everything that is our inference is marked TODO(reactor) and must
be checked before anyone claims this ran live.

What the docs gave us [docs]:
  - base URL                https://api.reactor.inc
  - auth                    API key `rk_...` in REACTOR_API_KEY; the Python SDK
                            exchanges it for a JWT internally (server-side token
                            mint is POST https://api.reactor.inc/tokens)
  - transport               persistent WebSocket, bidirectional, sub-second RTT
  - python package          `pip install reactor-sdk`
  - construction            Reactor(model_name="reactor/helios", api_key=...)
  - commands                await reactor.send_command("set_prompt", {"prompt": ...})
                            await reactor.send_command("start", {})
  - frames                  a frame callback receives (H, W, 3) uint8 RGB numpy

TODO(reactor) — fill these in against a live key before going live:
  1. BASE URL / MODEL SLUG: confirm the model slug to use. "reactor/helios" is
     the docs' example; do not guess an alternative.
  2. AUTH: confirm whether passing api_key= to Reactor(...) is sufficient, or
     whether we must mint a JWT ourselves (POST /tokens) and pass that.
     Confirm the exact header name if we ever call the REST surface directly.
  3. OUTPUT HANDLE: the docs show `@output.on_frame`. Confirm how `output` is
     obtained from the Reactor object (attribute? await reactor.output()?
     a trackReceived event carrying the "main_video" track?).
  4. REQUEST SHAPE: confirm whether an image-conditioned or video-conditioned
     mode exists. We currently drive it prompt-only, which is weaker than we
     want: we have a SceneGraph, and ideally we would condition on a rendered
     layout image rather than a text description of it.
  5. CONTROL: confirm the command to change the prompt mid-stream without
     tearing down the session (we assume a second "set_prompt" works), and the
     command to stop ("stop"? "pause"?).
  6. FRAME ENCODING: converting the numpy frame to a data URL needs Pillow,
     which is deliberately NOT in requirements.txt. Add `pillow` when going
     live, or switch the UI to a binary WebSocket frame channel.

See docs/PROVIDER_SWAP.md for the ten-minute checklist.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from ..scene_graph import SceneGraph
from .base import Frame, RenderRequest, WorldModelProvider
from .mock import MockProvider

log = logging.getLogger("skopos.reactor")

DEFAULT_MODEL = os.getenv("REACTOR_MODEL", "reactor/helios")  # [docs] example slug


def scene_to_prompt(sg: SceneGraph, req: RenderRequest) -> str:
    """Turn a SceneGraph into a text prompt.

    This is the weakest link in the whole adapter and we say so: a text prompt
    throws away the metric layout we spent perception extracting. See
    TODO(reactor) item 4 — image conditioning is the right answer.
    """
    bits: List[str] = []
    for o in sg.objects[:14]:
        desc = o.label
        if o.material != "unknown":
            desc = o.material + " " + desc
        bits.append("{} at ({:.1f}, {:.1f})".format(desc, o.pose.x, o.pose.y))
    light = "dim" if sg.lighting.level < 0.35 else ("bright" if sg.lighting.level > 0.75 else "evenly lit")
    if sg.lighting.glare > 0.4:
        light += ", strong specular glare"
    return (
        "Photorealistic interior, eye-level view of a {} living room with {} floor. "
        "Objects: {}. Camera slowly moving forward towards the table."
    ).format(light, sg.floor_type, "; ".join(bits))


class ReactorProvider(WorldModelProvider):
    """Streams from Reactor when a key and SDK are present, else falls back loudly.

    Threading model: the SDK is asyncio and push-based; our interface is a
    synchronous pull (`render`). So we run the SDK's loop on a background thread
    and keep only the most recent frame. `render()` returns that frame. If no
    frame has arrived yet we return the mock render rather than a blank screen,
    tagged so the UI can say which is which.
    """

    name = "reactor"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.api_key = os.getenv("REACTOR_API_KEY", "")
        self._fallback = MockProvider()
        self._latest: Optional[bytes] = None      # most recent PNG bytes
        self._latest_at: float = 0.0
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._reactor = None
        self._last_prompt: str = ""
        self.live = False
        self.status = "not started"

        if not self.api_key:
            self.status = "no REACTOR_API_KEY — using mock frames"
            log.warning("Reactor provider selected but REACTOR_API_KEY is unset; "
                        "serving MOCK frames. See docs/PROVIDER_SWAP.md.")
            return
        try:
            import reactor_sdk  # noqa: F401
        except ImportError:
            self.status = "reactor-sdk not installed — using mock frames"
            log.warning("reactor-sdk is not installed; serving MOCK frames. "
                        "pip install reactor-sdk")
            return
        self._start()

    # ------------------------------------------------------------ connection
    def _start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="reactor-stream")
        self._thread.start()
        self.status = "connecting"

    def _run_loop(self) -> None:
        """Background asyncio loop owning the Reactor session. [docs]-shaped."""
        import asyncio

        async def main() -> None:
            from reactor_sdk import Reactor  # [docs]

            reactor = Reactor(model_name=self.model, api_key=self.api_key)  # [docs]
            self._reactor = reactor

            # TODO(reactor) item 3: confirm how the output handle is obtained.
            output = getattr(reactor, "output", None)
            if output is None:
                raise RuntimeError(
                    "TODO(reactor): could not find the frame output handle on the "
                    "Reactor object. Check the SDK for how `@output.on_frame` is "
                    "wired up (docs show the decorator but not where `output` "
                    "comes from)."
                )

            @output.on_frame  # [docs]
            def on_frame(frame: Any) -> None:            # (H, W, 3) uint8 RGB [docs]
                png = self._encode_png(frame)
                if png is not None:
                    with self._lock:
                        self._latest = png
                        self._latest_at = time.time()
                    self.live = True
                    self.status = "streaming"

            await reactor.connect()                                    # [docs]
            await reactor.send_command("start", {})                    # [docs]
            await asyncio.Event().wait()

        try:
            asyncio.run(main())
        except Exception as exc:            # noqa: BLE001 — never kill the demo
            self.live = False
            self.status = "error: {}".format(exc)
            log.exception("Reactor stream failed; falling back to mock frames")

    @staticmethod
    def _encode_png(frame: Any) -> Optional[bytes]:
        """numpy (H,W,3) uint8 -> PNG bytes. Needs Pillow; see TODO(reactor) 6."""
        try:
            from PIL import Image
        except ImportError:
            log.error("Pillow is not installed; cannot encode Reactor frames. "
                      "pip install pillow")
            return None
        buf = io.BytesIO()
        Image.fromarray(frame).save(buf, format="PNG", optimize=False)
        return buf.getvalue()

    # ---------------------------------------------------------------- render
    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame:
        t0 = time.perf_counter()

        # Push a new prompt when the scene changes. TODO(reactor) item 5.
        prompt = scene_to_prompt(sg, req)
        if self._reactor is not None and prompt != self._last_prompt:
            self._last_prompt = prompt
            try:
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    self._reactor.send_command("set_prompt", {"prompt": prompt}),  # [docs]
                    self._reactor_loop(),
                )
            except Exception as exc:        # noqa: BLE001
                log.warning("set_prompt failed: %s", exc)

        with self._lock:
            png, at = self._latest, self._latest_at

        if png is not None and (time.time() - at) < 2.0:
            b64 = base64.b64encode(png).decode("ascii")
            return Frame(
                data_url="data:image/png;base64," + b64,
                provider=self.name,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                step=req.step,
                meta={"live": True, "model": self.model, "age_s": round(time.time() - at, 3)},
            )

        frame = self._fallback.render(sg, req)
        frame.provider = "reactor(fallback:mock)"
        frame.meta["live"] = False
        frame.meta["reason"] = self.status
        return frame

    def _reactor_loop(self):
        """TODO(reactor): the SDK does not document how to reach its event loop.

        Returns the loop the background thread is running so we can schedule
        commands onto it. Replace with whatever the SDK exposes.
        """
        import asyncio
        loop = getattr(self._reactor, "_loop", None)
        if loop is None:
            raise RuntimeError("TODO(reactor): no accessible event loop on the SDK object")
        return loop

    def health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "live": self.live,
            "ok": True,
            "status": self.status,
            "model": self.model,
            "key_present": bool(self.api_key),
            "note": "adapter written from docs, never executed against the live API",
        }

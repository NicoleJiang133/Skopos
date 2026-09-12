"""
Reactor (reactor.inc) world-model provider.

STATUS: written against `reactor-sdk` 1.5.1, whose real API was read directly
off the installed package (signatures and docstrings), not guessed. What remains
unverified is only what needs a live key and a live model: the model slug, the
command names that model actually declares, and whether frames arrive at a
useful rate. `scripts/reactor_probe.py` answers all three in one run — do that
before relying on anything here.

HOW THE SDK ACTUALLY WORKS (from reactor_sdk 1.5.1)
---------------------------------------------------
    reactor = Reactor(model_name="reactor/helios", api_key=...)   # or jwt=...
    await reactor.connect()                    # WebRTC transport, status -> "ready"

    @reactor.on_track                          # fires once per incoming track
    def got(track):
        if track.kind == TrackKind.VIDEO:
            @track.on_frame                    # RGB numpy (H, W, 3)
            def frame(frame, frame_id, timestamp_us, user_data): ...

    schema = await reactor.request_schema()    # the model's OWN command schema
    reply  = await reactor.send_command(name, data)

    ref = await reactor.upload_file("room.jpg")          # -> FileRef, needs READY
    await reactor.send_command("set_image", {"image": ref})

Two SDK details that shape the code below:

* `upload_file` raises `InvalidStateError` unless the connection is already
  `"ready"`, so reference images are uploaded from a READY status handler, never
  at construction time.
* We create and own the asyncio loop the SDK runs on, so commands are scheduled
  from the render thread with `run_coroutine_threadsafe` against *our* loop. The
  earlier version of this file reached for a private `reactor._loop`; it does
  not need to and no longer does.

PRIVACY — READ THIS BEFORE ENABLING REFERENCE IMAGES
-----------------------------------------------------
Skopos's headline claim is that no pixels leave the device. Uploading a
photograph of the real room as a generation reference **breaks that claim**: the
photo is pixels, and it goes to Reactor.

So it is opt-in and off by default. With `SKOPOS_REFERENCE_IMAGES` unset, the
only thing that ever leaves is the scene graph, exactly as the README says. Set
it and the app says so, loudly, in the provider badge and the privacy panel —
because the alternative is a privacy claim on screen that is not true.

If you want the visual anchoring without the privacy cost, point it at a
*rendered* reference (the mock provider's own plan view, or any synthetic image
derived from the scene graph) rather than a photo. Same mechanism, no real
pixels.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from engine import SceneGraph

from .base import Frame, RenderRequest, WorldModelProvider
from .mock import MockProvider

log = logging.getLogger("skopos.reactor")

DEFAULT_MODEL = os.getenv("REACTOR_MODEL", "reactor/helios")
DEFAULT_API_URL = os.getenv("REACTOR_API_URL", "https://api.reactor.inc")

# Command names. The docs and the SDK's own docstrings both use these, but the
# authoritative answer is `request_schema()` for your model — the probe script
# prints it, and these are overridable rather than hard-coded.
PROMPT_COMMAND = os.getenv("REACTOR_PROMPT_COMMAND", "set_prompt")
PROMPT_FIELD = os.getenv("REACTOR_PROMPT_FIELD", "prompt")
START_COMMAND = os.getenv("REACTOR_START_COMMAND", "start")
IMAGE_COMMAND = os.getenv("REACTOR_IMAGE_COMMAND", "set_image")
IMAGE_FIELD = os.getenv("REACTOR_IMAGE_FIELD", "image")

# Comma-separated paths. Off by default; see the privacy note above.
REFERENCE_IMAGES = [
    p.strip() for p in os.getenv("SKOPOS_REFERENCE_IMAGES", "").split(",") if p.strip()
]

# A frame older than this is treated as stale and we fall back rather than show
# a frozen picture while claiming it is live.
FRAME_STALE_SECONDS = float(os.getenv("REACTOR_FRAME_STALE_S", "2.0"))
# How long render() will wait for the stream to catch up with a new prompt.
PROMPT_SETTLE_SECONDS = float(os.getenv("REACTOR_PROMPT_SETTLE_S", "0.0"))


def scene_to_prompt(sg: SceneGraph, req: RenderRequest) -> str:
    """Turn a scene graph into a text prompt.

    Text is a lossy channel for geometry — it throws away the layout the
    surrogate actually scores on. Reference images (or, better, an image-
    conditioned mode if the model has one) are how you get that back.
    """
    bits: List[str] = []
    for it in sg.items:
        if not it.present:
            continue
        desc = it.name.replace("_", " ")
        if it.reflective:
            desc = "glossy reflective " + desc
        elif it.low_contrast:
            desc = "matte black " + desc
        bits.append("{} at ({:.1f}, {:.1f})".format(desc, it.x, it.y))

    missing = [it.name.replace("_", " ") for it in sg.items if not it.present]
    light = "dimly lit" if sg.lighting < 0.35 else (
        "brightly lit" if sg.lighting > 0.75 else "evenly lit")

    parts = [
        "Photorealistic interior, eye-level view of a {} living room.".format(light),
        "Objects: {}.".format("; ".join(bits) if bits else "an empty room"),
    ]
    if sg.clutter:
        parts.append("{} small unmodelled objects scattered across the floor.".format(sg.clutter))
    if missing:
        parts.append("The {} is not present.".format(", ".join(missing)))
    parts.append("Camera moving slowly towards the {}.".format(sg.target))
    return " ".join(parts)


class ReactorProvider(WorldModelProvider):
    """Streams frames from Reactor, falling back to the mock renderer loudly.

    Threading: the SDK is asyncio and push-based; our interface is a synchronous
    pull (`render`). So the SDK runs on a loop we own on a background thread and
    we keep only the most recent frame. `render()` returns that frame, or the
    mock render tagged `live: False` if none has arrived.
    """

    name = "reactor"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.api_key = os.getenv("REACTOR_API_KEY", "")
        self.api_url = DEFAULT_API_URL
        self._fallback = MockProvider()

        self._latest_png: Optional[bytes] = None
        self._latest_at: float = 0.0
        self._frames_in = 0
        self._lock = threading.Lock()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._reactor: Any = None
        self._thread: Optional[threading.Thread] = None
        self._last_prompt = ""
        self._schema: Optional[Dict[str, Any]] = None
        self._uploaded: List[str] = []

        self.live = False
        self.status = "not started"
        self.reference_images = list(REFERENCE_IMAGES)

        if not self.api_key:
            self.status = "no REACTOR_API_KEY — serving mock frames"
            log.warning("Reactor selected but REACTOR_API_KEY is unset; serving MOCK "
                        "frames. See docs/PROVIDER_SWAP.md.")
            return
        try:
            import reactor_sdk  # noqa: F401
        except ImportError:
            self.status = "reactor-sdk not installed — serving mock frames"
            log.warning("pip install reactor-sdk pillow numpy; serving MOCK frames.")
            return

        if self.reference_images:
            log.warning(
                "PRIVACY: SKOPOS_REFERENCE_IMAGES is set. %d image(s) will be uploaded "
                "to Reactor. Pixels WILL leave this device. %s",
                len(self.reference_images), self.reference_images)
        self._start()

    # ------------------------------------------------------------ connection
    def _start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="reactor-stream")
        self._thread.start()
        self.status = "connecting"

    def _run_loop(self) -> None:
        """Own the loop, so commands can be scheduled onto it from render()."""
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception as exc:            # noqa: BLE001 — never kill the demo
            self.live = False
            self.status = "error: {}".format(exc)
            log.exception("Reactor stream failed; falling back to mock frames")
        finally:
            try:
                loop.close()
            finally:
                self._loop = None

    async def _main(self) -> None:
        from reactor_sdk import Reactor, ReactorStatus, TrackKind

        reactor = Reactor(model_name=self.model, api_key=self.api_key,
                          api_url=self.api_url)
        self._reactor = reactor

        @reactor.on_track
        def _on_track(track: Any) -> None:
            # Fires once per incoming track; not filtered by name, so check.
            if str(track.kind) != str(TrackKind.VIDEO):
                return
            log.info("Reactor video track: %s", track.name)

            @track.on_frame
            def _on_frame(frame: Any) -> None:      # RGB numpy (H, W, 3)
                png = self._encode_png(frame)
                if png is None:
                    return
                with self._lock:
                    self._latest_png = png
                    self._latest_at = time.time()
                    self._frames_in += 1
                if not self.live:
                    self.live = True
                    self.status = "streaming"

        @reactor.on_status
        def _on_status(status: Any) -> None:
            log.info("Reactor status: %s", status)
            if not self.live:
                self.status = "status: {}".format(status)

        @reactor.on_error
        def _on_error(err: Any) -> None:
            log.error("Reactor error: %s", err)
            self.status = "error: {}".format(err)

        await reactor.connect()
        self.status = "connected"

        # The model's own command schema. Logged so the real command names are
        # visible in the run rather than assumed.
        try:
            self._schema = await reactor.request_schema()
            log.info("Reactor command schema keys: %s",
                     sorted(self._schema.get("paths", self._schema).keys())[:20])
        except Exception as exc:            # noqa: BLE001
            log.warning("request_schema() failed (continuing): %s", exc)

        # upload_file requires READY, which connect() has now guaranteed.
        await self._upload_references(reactor)

        try:
            await reactor.send_command(START_COMMAND, {})
        except Exception as exc:            # noqa: BLE001
            log.warning("%s command failed (continuing): %s", START_COMMAND, exc)

        # Hold the loop open for the life of the process.
        await asyncio.Event().wait()

    async def _upload_references(self, reactor: Any) -> None:
        """Upload the configured reference images and hand them to the model.

        Opt-in: with SKOPOS_REFERENCE_IMAGES unset this does nothing and no
        pixels leave the device.
        """
        if not self.reference_images:
            return
        refs = []
        for path in self.reference_images:
            if not os.path.exists(path):
                log.error("reference image not found, skipping: %s", path)
                continue
            try:
                ref = await reactor.upload_file(path)
                refs.append(ref)
                self._uploaded.append(os.path.basename(path))
                log.info("uploaded reference image: %s", path)
            except Exception as exc:        # noqa: BLE001
                log.error("upload failed for %s: %s", path, exc)
        if not refs:
            return
        # Single ref goes in the top-level slot the SDK pulls out as an upload
        # reference; several go in a list, serialised in place.
        data = {IMAGE_FIELD: refs[0]} if len(refs) == 1 else {IMAGE_FIELD: refs}
        try:
            await reactor.send_command(IMAGE_COMMAND, data)
            log.info("sent %s with %d reference image(s)", IMAGE_COMMAND, len(refs))
        except Exception as exc:            # noqa: BLE001
            log.error("%s failed — check the model's schema for the right command "
                      "and field name: %s", IMAGE_COMMAND, exc)

    # ---------------------------------------------------------------- frames
    @staticmethod
    def _encode_png(frame: Any) -> Optional[bytes]:
        """RGB numpy (H, W, 3) -> PNG bytes."""
        try:
            from PIL import Image
        except ImportError:
            log.error("Pillow is not installed; cannot encode Reactor frames. "
                      "pip install pillow")
            return None
        try:
            buf = io.BytesIO()
            Image.fromarray(frame).save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:            # noqa: BLE001
            log.error("frame encode failed: %s", exc)
            return None

    def _send(self, command: str, data: Any) -> None:
        """Fire a command from the render thread onto the SDK's loop."""
        loop, reactor = self._loop, self._reactor
        if loop is None or reactor is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(reactor.send_command(command, data), loop)
        except Exception as exc:            # noqa: BLE001
            log.warning("%s failed: %s", command, exc)

    # ---------------------------------------------------------------- render
    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame:
        t0 = time.perf_counter()

        prompt = scene_to_prompt(sg, req)
        if prompt != self._last_prompt:
            self._last_prompt = prompt
            self._send(PROMPT_COMMAND, {PROMPT_FIELD: prompt})
            if PROMPT_SETTLE_SECONDS > 0:
                # Give the stream a moment to reflect the new prompt. Off by
                # default: it trades demo pace for fidelity.
                time.sleep(PROMPT_SETTLE_SECONDS)

        with self._lock:
            png, at, n = self._latest_png, self._latest_at, self._frames_in

        age = time.time() - at if png is not None else None
        if png is not None and age is not None and age < FRAME_STALE_SECONDS:
            return Frame(
                data_url="data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                provider=self.name,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                step=req.step,
                meta={"live": True, "model": self.model, "age_s": round(age, 3),
                      "frames_in": n, "severity": round(req.severity, 3),
                      "culprit": req.culprit,
                      "reference_images": len(self._uploaded)},
            )

        frame = self._fallback.render(sg, req)
        frame.provider = "reactor(fallback:mock)"
        frame.meta["live"] = False
        frame.meta["reason"] = (
            "no frame yet — " + self.status if png is None
            else "last frame is {:.1f}s old — {}".format(age or 0.0, self.status))
        return frame

    def health(self) -> Dict[str, Any]:
        with self._lock:
            n, at = self._frames_in, self._latest_at
        return {
            "provider": self.name,
            "live": self.live,
            "ok": True,
            "status": self.status,
            "model": self.model,
            "api_url": self.api_url,
            "key_present": bool(self.api_key),
            "frames_in": n,
            "last_frame_age_s": round(time.time() - at, 2) if at else None,
            "reference_images": list(self._uploaded),
            # Surfaced so the UI can contradict the privacy banner when it must.
            "pixels_uploaded": bool(self._uploaded),
            "schema_known": self._schema is not None,
        }

    def close(self) -> None:
        loop, reactor = self._loop, self._reactor
        if loop is not None and reactor is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(reactor.disconnect(), loop).result(5)
            except Exception:               # noqa: BLE001
                pass

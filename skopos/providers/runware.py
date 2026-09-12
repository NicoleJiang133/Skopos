"""
Runware fallback provider — STUB.

Same interface as every other provider. Not executed against the live API; we
had no key. Runware's public surface is a WebSocket/REST image-generation API,
so the natural shape is: SceneGraph -> prompt -> image task -> URL -> frame.

TODO(runware) — fill in against a live key:
  1. BASE URL: confirm (docs point at wss://ws-api.runware.ai/v1 for the socket
     API and https://api.runware.ai/v1 for REST). Do not guess.
  2. AUTH: confirm whether auth is an initial {"taskType":"authentication",
     "apiKey": ...} frame on the socket, a Bearer header on REST, or both.
  3. REQUEST SHAPE: confirm the imageInference task fields — taskUUID,
     positivePrompt, model, width/height, numberResults, outputFormat.
  4. RESPONSE: confirm where the image comes back (imageURL vs imageBase64Data)
     and set outputType accordingly; we want base64 so nothing extra is fetched.
  5. RATE/LATENCY: this is a per-image API, not a real-time stream. Decide
     whether to render one frame per attempt rather than per step.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict

from ..scene_graph import SceneGraph
from .base import Frame, RenderRequest, WorldModelProvider
from .mock import MockProvider
from .reactor import scene_to_prompt

log = logging.getLogger("skopos.runware")


class RunwareProvider(WorldModelProvider):
    name = "runware"

    def __init__(self) -> None:
        self.api_key = os.getenv("RUNWARE_API_KEY", "")
        self._fallback = MockProvider()
        self.live = False
        self.status = ("no RUNWARE_API_KEY — using mock frames" if not self.api_key
                       else "stub: request path not implemented, see TODO(runware)")
        if self.api_key:
            log.warning("Runware key present but the adapter is a stub; serving MOCK frames.")

    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame:
        _ = scene_to_prompt(sg, req)   # the prompt we would send
        frame = self._fallback.render(sg, req)
        frame.provider = "runware(fallback:mock)"
        frame.meta["live"] = False
        frame.meta["reason"] = self.status
        return frame

    def health(self) -> Dict[str, Any]:
        return {
            "provider": self.name, "live": False, "ok": True, "status": self.status,
            "key_present": bool(self.api_key),
            "note": "stub only — never executed against the live API",
        }

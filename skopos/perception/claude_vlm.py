"""
Vision perception via the Claude API: frames in, SceneGraph out.

This is the one place in Skopos that ever sees pixels, and it is written so the
pixels do not survive it:
  - frames are passed in memory, base64-encoded inline into one request, and the
    local references are dropped before the function returns;
  - nothing is written to disk;
  - what comes back is JSON, and that JSON is all that continues downstream.

The network boundary is therefore *inside* this module. That is a real caveat
and the README states it: if you run with SKOPOS_PERCEPTION=claude, your frames
go to the Claude API once. The default is the mock backend, which never leaves
the machine.

Not executed during the build (we ran the mock path), so treat this as
untested-against-real-frames — the request shape follows the documented Messages
API image block format.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import List, Optional

from ..privacy import PrivacyLedger
from ..scene_graph import HAZARD_FLAGS, MATERIALS, SceneGraph
from .base import PerceptionBackend
from .mock import demo_room

log = logging.getLogger("skopos.perception")

MODEL = os.getenv("SKOPOS_VLM_MODEL", "claude-sonnet-5")

SYSTEM = (
    "You are a robot perception front-end. You convert images of a room into a "
    "semantic scene graph. You output JSON only, no prose, no code fences."
)

PROMPT = """Return a JSON object with exactly these keys:

{{
  "objects": [
    {{"id": "snake_case_unique_id",
      "label": "short noun",
      "pose": {{"x": float, "y": float, "z": float, "yaw": 0.0}},
      "extent": [width_m, depth_m, height_m],
      "material": one of {materials},
      "hazard_flags": subset of {hazards},
      "movable": bool,
      "confidence": 0.0-1.0,
      "support": "floor" or the id of the object it rests on}}
  ],
  "lighting": {{"level": 0.0-1.0, "color_temp_k": int, "directional": bool, "glare": 0.0-1.0}},
  "floor_type": "hardwood" | "carpet" | "tile" | "laminate",
  "free_space_ratio": 0.0-1.0
}}

Coordinates are in metres in a room-local frame with the camera's first pose at
the origin, x to the right, y away from the camera. Approximate is fine and
expected — say what you see, do not invent precision you do not have. Set
confidence honestly and low when you are unsure.
"""


class ClaudeVLMPerception(PerceptionBackend):
    name = "claude"

    def __init__(self, model: str = MODEL) -> None:
        self.model = model
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.available = bool(self.api_key)
        if not self.available:
            log.warning("ANTHROPIC_API_KEY unset; Claude perception will fall back "
                        "to the hand-authored demo room.")

    def scene_from_frames(
        self,
        frames: List[bytes],
        ledger: Optional[PrivacyLedger] = None,
        room_id: str = "scanned-room",
    ) -> SceneGraph:
        if ledger is not None:
            ledger.note_frames(len(frames))

        if not self.available or not frames:
            sg = demo_room(room_id)
            sg.notes = ("fallback: hand-authored demo room (no ANTHROPIC_API_KEY "
                        "or no frames supplied)")
            if ledger is not None:
                sg.frames_seen, sg.frames_retained = ledger.frames_seen, ledger.frames_retained
            return sg

        try:
            payload = self._call(frames)
        except Exception as exc:   # noqa: BLE001 — perception must never kill the demo
            log.exception("Claude perception failed; falling back to the demo room")
            sg = demo_room(room_id)
            sg.notes = "fallback after perception error: {}".format(exc)
            return sg
        finally:
            # Drop every local reference to pixels before returning, in both
            # the success and failure paths.
            frames = []
            del frames

        payload["room_id"] = room_id
        payload.setdefault("notes", "scanned via {}; poses approximate, no metric "
                                    "ground truth".format(self.model))
        sg = SceneGraph.from_dict(payload)
        if ledger is not None:
            sg.frames_seen, sg.frames_retained = ledger.frames_seen, ledger.frames_retained
        return sg

    # ------------------------------------------------------------------ http
    def _call(self, frames: List[bytes], max_images: int = 6) -> dict:
        import httpx

        # Spread the sample across the clip rather than taking the first N.
        step = max(1, len(frames) // max_images)
        chosen = frames[::step][:max_images]

        content: List[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(f).decode("ascii"),
                },
            }
            for f in chosen
        ]
        content.append({
            "type": "text",
            "text": PROMPT.format(materials=list(MATERIALS), hazards=list(HAZARD_FLAGS)),
        })

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 3000,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": content}],
            },
            timeout=90.0,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)

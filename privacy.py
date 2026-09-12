"""
Privacy accounting.

The rule: frames are turned into a SceneGraph in memory and then dropped. The
only artefact that survives perception — and the only thing that ever crosses a
network boundary — is structured text.

The single escape hatch is SKOPOS_DEBUG_KEEP_FRAMES=1, which is off by default
and shouted about at startup when it is on.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict

DEBUG_KEEP_FRAMES = os.getenv("SKOPOS_DEBUG_KEEP_FRAMES", "0") == "1"

ASSERTION = (
    "PRIVACY: frames are processed in memory and discarded; only the SceneGraph "
    "(structured text, no pixels) leaves this device."
)


@dataclass
class PrivacyLedger:
    frames_seen: int = 0
    frames_discarded: int = 0
    frames_retained: int = 0
    bytes_out: int = 0          # cumulative SceneGraph JSON bytes sent over the wire
    payloads_out: int = 0

    def note_frames(self, n: int) -> None:
        self.frames_seen += n
        if DEBUG_KEEP_FRAMES:
            self.frames_retained += n
        else:
            self.frames_discarded += n

    def note_payload(self, payload: str) -> None:
        self.payloads_out += 1
        self.bytes_out += len(payload.encode("utf-8"))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["debug_keep_frames"] = DEBUG_KEEP_FRAMES
        d["assertion"] = ASSERTION
        return d


def startup_assertion() -> str:
    line = ASSERTION
    if DEBUG_KEEP_FRAMES:
        line += "  [!! SKOPOS_DEBUG_KEEP_FRAMES=1 — RAW FRAMES ARE BEING WRITTEN TO DISK !!]"
    return line

"""Perception interface: pixels in, SceneGraph out. Pixels stop here."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..privacy import PrivacyLedger
from ..scene_graph import SceneGraph


class PerceptionBackend(ABC):
    name: str = "base"

    @abstractmethod
    def scene_from_frames(
        self,
        frames: List[bytes],
        ledger: Optional[PrivacyLedger] = None,
        room_id: str = "demo-room",
    ) -> SceneGraph:
        """Consume frames, return a SceneGraph, and retain nothing.

        Implementations MUST NOT persist `frames` anywhere.
        """
        raise NotImplementedError

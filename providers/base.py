"""
World-model provider interface.

A provider turns a `SceneGraph` (from engine.py) into frames. The scene graph is
the only input: providers never see the user's original pixels.

Rendering is expensive, which is the whole reason `engine.surrogate` exists. We
score tens of thousands of configurations on the scene graph and render only
`campaign.elite(k)` — the worst handful.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine import SceneGraph


@dataclass
class RenderRequest:
    seed: int = 0
    step: int = 0
    severity: float = 0.0                 # surrogate severity of this configuration
    rank: int = 0                         # position within the elite set
    of: int = 0                           # size of the elite set
    strategy: Optional[str] = None        # the arm being attempted
    culprit: Optional[str] = None         # attributed object, from the surrogate
    agent_xy: Optional[List[float]] = None
    path: Optional[List[List[float]]] = None
    status: str = "running"               # running | success | fail


@dataclass
class Frame:
    """One rendered frame. `data_url` is directly usable as an <img> src."""
    data_url: str
    provider: str
    latency_ms: float
    step: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_url": self.data_url,
            "provider": self.provider,
            "latency_ms": round(self.latency_ms, 2),
            "step": self.step,
            "meta": self.meta,
        }


class WorldModelProvider(ABC):
    name: str = "base"
    live: bool = False          # True only when actually hitting a remote API

    @abstractmethod
    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame:
        ...

    def set_reference_scene(self, sg: SceneGraph) -> None:
        """The base room changed; update any conditioning derived from it.

        No-op for providers that do not condition on an image. Called with the
        *unperturbed* scene, which `render()` cannot identify on its own.
        """
        return None

    def health(self) -> Dict[str, Any]:
        return {"provider": self.name, "live": self.live, "ok": True}

    def close(self) -> None:
        pass

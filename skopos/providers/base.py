"""
World-model provider interface.

A provider turns a SceneGraph (+ a little render state) into frames. The
SceneGraph is the only input; providers never see the user's original pixels.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..scene_graph import SceneGraph


@dataclass
class RenderRequest:
    seed: int = 0
    step: int = 0
    severity: float = 0.0                 # 0-1 aggregate perturbation severity
    strategy: Optional[str] = None        # the arm currently being attempted
    agent_xy: Optional[list] = None       # [x, y] of the simulated agent
    path: Optional[list] = None           # [[x,y], ...] attempted trajectory
    status: str = "running"               # running | success | fail
    hazard_hit: Optional[str] = None


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

    def health(self) -> Dict[str, Any]:
        return {"provider": self.name, "live": self.live, "ok": True}

    def close(self) -> None:
        pass

"""
Run state: one Skopos session = one room, one prior, one bandit, one metrics store.

Single-session by design. This is a demo, not a service.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .agent.bandit import ARMS, LinUCBBandit
from .agent.task import Episode, run_episode
from .metrics.readiness import AttemptRecord, MetricsStore
from .perception.base import PerceptionBackend
from .perception.mock import MockPerception
from .privacy import PrivacyLedger, startup_assertion
from .providers.base import Frame, RenderRequest, WorldModelProvider
from .providers.mock import MockProvider
from .sampler.monte_carlo import SampledRoom, sample_room
from .sampler.prior import AXES, AXIS_DESC, PerturbationPrior
from .scene_graph import SceneGraph, context_vector

DEFAULT_SEED = 20260912


@dataclass
class SessionConfig:
    seed: int = DEFAULT_SEED
    resample_every: int = 8          # attempts per sampled room
    frames_per_attempt: int = 7
    frame_interval_ms: int = 70
    window: int = 25


class Session:
    def __init__(
        self,
        provider: Optional[WorldModelProvider] = None,
        perception: Optional[PerceptionBackend] = None,
        config: Optional[SessionConfig] = None,
    ) -> None:
        self.config = config or SessionConfig()
        self.provider: WorldModelProvider = provider or MockProvider()
        self.perception: PerceptionBackend = perception or MockPerception()
        self.ledger = PrivacyLedger()
        self.prior = PerturbationPrior.default()
        self.reset(self.config.seed)

    # ------------------------------------------------------------------ setup
    def reset(self, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.config.seed = seed
        self.rng = random.Random(self.config.seed)
        self.ledger = PrivacyLedger()
        # "Scan": synthetic frames in, SceneGraph out, frames dropped.
        synthetic_frames = [b"<frame>"] * 42
        self.base_graph: SceneGraph = self.perception.scene_from_frames(
            synthetic_frames, self.ledger
        )
        self.bandit = LinUCBBandit()
        self.metrics = MetricsStore(window=self.config.window)
        self.attempt_index = 0
        self.room_attempts = 0
        self.current: SampledRoom = self._sample_room()
        self.last_episode: Optional[Episode] = None
        self.started_at = time.time()

    def _sample_room(self) -> SampledRoom:
        room = sample_room(self.base_graph, self.prior, self.rng, seed=self.config.seed)
        self.room_attempts = 0
        return room

    def shift_room(self) -> SampledRoom:
        self.current = self._sample_room()
        return self.current

    # --------------------------------------------------------------- controls
    def _prior_changed(self) -> None:
        """Changing the prior invalidates every measurement taken under the old one.

        This is not housekeeping, it is correctness. Each sample carries an
        importance weight w = p(room)/q(room) computed against a *specific*
        prior p. Move the sliders and p is a different distribution, so the old
        weighted samples no longer estimate E_p[.] for the new p and must not be
        pooled with the new ones. So the metrics store is rebuilt.

        The bandit is deliberately NOT reset: it estimates arm value as a
        function of the room context, which is unchanged by a change in how
        often we draw a given kind of room.
        """
        self.metrics = MetricsStore(window=self.config.window)

    def set_rates(self, rates: Dict[str, float]) -> bool:
        changed = False
        for k, v in rates.items():
            if k in AXES:
                v = max(0.0, min(1.0, float(v)))
                if abs(self.prior.rates.get(k, 0.0) - v) > 1e-9:
                    changed = True
                self.prior.rates[k] = v
        if changed:
            self._prior_changed()
        return changed

    def set_tilt(self, tilt: float) -> bool:
        tilt = max(0.0, min(1.0, float(tilt)))
        changed = abs(self.prior.tilt - tilt) > 1e-9
        self.prior.tilt = tilt
        if changed:
            self._prior_changed()
        return changed

    # ------------------------------------------------------------- one attempt
    def step(self) -> Dict[str, Any]:
        """Run one attempt in the current room. Returns everything the UI needs."""
        if self.room_attempts >= self.config.resample_every:
            self.current = self._sample_room()

        sg = self.current.graph
        x = context_vector(sg)
        arm = self.bandit.select(x)
        ep = run_episode(sg, arm, self.rng)
        self.bandit.update(arm, x, ep.reward, ep.success)

        self.attempt_index += 1
        self.room_attempts += 1
        rec = AttemptRecord(
            index=self.attempt_index, arm=ep.arm, success=ep.success, reward=ep.reward,
            seconds=ep.seconds, hazard_hit=ep.hazard_hit, hazard_object=ep.hazard_object,
            failure_reason=ep.failure_reason, weight=self.current.weight,
            severity=self.current.severity, room=sg.room_id, deferred=ep.deferred,
        )
        self.metrics.add(rec)
        self.last_episode = ep
        return {"episode": ep, "arm": arm, "context": x}

    # --------------------------------------------------------------- payloads
    def scene_payload(self) -> str:
        """The exact JSON that would cross a network boundary. Nothing else does."""
        payload = self.current.graph.to_json()
        self.ledger.note_payload(payload)
        return payload

    def render(self, ep: Optional[Episode], frac: float, step: int) -> Frame:
        path = ep.path if ep else None
        agent_xy = None
        status = "running"
        hazard = None
        if ep and path:
            i = min(int(frac * (len(path) - 1)), len(path) - 1)
            agent_xy = path[i]
            path = path[: i + 1]
            if frac >= 0.999:
                status = "success" if ep.success else "fail"
                hazard = ep.hazard_hit
        req = RenderRequest(
            seed=self.config.seed, step=step, severity=self.current.severity,
            strategy=ep.arm if ep else None, agent_xy=agent_xy, path=path,
            status=status, hazard_hit=hazard,
        )
        return self.provider.render(self.current.graph, req)

    def state(self) -> Dict[str, Any]:
        x = context_vector(self.current.graph)
        return {
            "seed": self.config.seed,
            "attempt": self.attempt_index,
            "room": self.current.to_dict(),
            "room_attempts": self.room_attempts,
            "resample_every": self.config.resample_every,
            "bandit": self.bandit.snapshot(x),
            "metrics": self.metrics.to_dict(),
            "privacy": self.ledger.to_dict(),
            "prior": self.prior.to_dict(),
            "axes": AXES,
            "axis_desc": AXIS_DESC,
            "arms": ARMS,
            "provider": self.provider.health(),
            "perception": self.perception.name,
            "assertion": startup_assertion(),
            "object_count": len(self.current.graph.objects),
        }

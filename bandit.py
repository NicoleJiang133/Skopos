"""
Contextual bandit over the four task strategies.

WHAT THIS IS AND IS NOT
-----------------------
A **contextual bandit**, not a trained policy. A bandit is the one-step case of
reinforcement learning: one decision, one reward, no state transition and no
credit assignment across time. Nothing here is trained and nothing here is a
learned policy. The verbs used throughout are *select*, *update* and *estimate*.

WHY LinUCB RATHER THAN EPSILON-GREEDY
-------------------------------------
1. The value of an arm genuinely depends on the room — a wide arc earns its
   detour only when something is actually near the path — and a linear model
   shares statistical strength across similar contexts, so the arms re-order
   within tens of pulls instead of hundreds. Epsilon-greedy with a context
   vector would need one independent estimate per context bucket.
2. LinUCB carries an explicit uncertainty term, alpha * sqrt(x' A^-1 x), which
   we draw on screen as the lighter part of each bar. Epsilon-greedy's
   exploration is an invisible coin flip: worse demo, worse argument.
3. It is closed form, so a replay of the same seed reproduces the same bars.

THE MATHS
---------
Per arm a we keep A_a = I_d + sum_t x_t x_t' and b_a = sum_t r_t x_t.
    theta_a = A_a^-1 b_a                        (ridge solution, lambda = 1)
    p_a     = theta_a . x + alpha * sqrt(x' A_a^-1 x)
Select argmax_a p_a, observe r in [0, 1], then A_a += x x', b_a += r x.

REWARD
------
Straight from engine.surrogate, which is the only scorer in this project:

    reward = (0.0 if failed(severity) else 1.0) - TIME_WEIGHT * time_cost(arm)

A binary task outcome minus a small penalty for slow strategies, so asking a
human wins only where the fast arms genuinely break.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from engine import STRATEGIES, Item, SceneGraph, apply, failed, surrogate

ARMS: List[str] = list(STRATEGIES)

ARM_BLURB: Dict[str, str] = {
    "direct_approach": "shortest path, no re-look",
    "wide_arc": "detour around flagged objects",
    "slow_scan_then_approach": "re-perceive, then move slowly",
    "request_human_assist": "stop and ask a human",
}

# Relative time cost per arm. These mirror engine.surrogate's own time_cost
# table, which the engine does not export; test_bandit_time_order() in
# selftest.py asserts the ordering still agrees with the engine, so this cannot
# drift out of sync silently.
ARM_TIME: Dict[str, float] = {
    "direct_approach": 0.0,
    "wide_arc": 0.4,
    "slow_scan_then_approach": 0.7,
    "request_human_assist": 1.6,
}
# Small relative to the 0/1 task outcome: time is a tie-breaker, not the point.
TIME_WEIGHT = 0.06

# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------
CONTEXT_FEATURES = (
    "bias",              # constant 1.0
    "darkness",          # 1 - lighting, 0 bright .. 1 pitch dark
    "clutter",           # unmodelled obstacle count, normalised
    "reflective_near",   # reflective items close to the robot's path
    "low_contrast_near", # low-contrast items close to the robot's path
)
CONTEXT_DIM = len(CONTEXT_FEATURES)

# "Near the path" means within this margin of the item's own footprint, matching
# the band engine.surrogate uses for its perception-failure term.
NEAR_MARGIN = 0.5


def _point_segment_distance(px: float, py: float, ax: float, ay: float,
                            bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    denom = vx * vx + vy * vy
    if denom < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / denom))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def context_vector(scene: SceneGraph) -> List[float]:
    """Map a scene graph to the fixed-length feature vector the bandit sees.

    Deliberately small and hand-readable: five numbers a judge can point at on
    screen and trace back to the JSON payload.
    """
    target = scene.get(scene.target)
    rx, ry = scene.robot
    if target is None:
        # No target: nothing is "near the path" because there is no path.
        return [1.0, 1.0 - scene.lighting, min(scene.clutter / 8.0, 1.0), 0.0, 0.0]

    tx, ty = target.x, target.y
    refl = low = 0.0
    for it in scene.items:
        if not it.present or it.name == scene.target:
            continue
        if not (it.reflective or it.low_contrast):
            continue
        d = _point_segment_distance(it.x, it.y, rx, ry, tx, ty)
        if d < it.radius + NEAR_MARGIN:
            if it.reflective:
                refl += 1.0
            if it.low_contrast:
                low += 1.0
    return [
        1.0,
        1.0 - scene.lighting,
        min(scene.clutter / 8.0, 1.0),
        min(refl / 3.0, 1.0),
        min(low / 3.0, 1.0),
    ]


def reward_for(scene: SceneGraph, arm: str) -> tuple:
    """Evaluate one arm in one scene. Returns (reward, failed, severity, culprit)."""
    severity, culprit = surrogate(scene, arm)
    did_fail = failed(severity)
    r = (0.0 if did_fail else 1.0) - TIME_WEIGHT * ARM_TIME.get(arm, 0.0)
    return max(0.0, min(1.0, r)), did_fail, severity, culprit


# ---------------------------------------------------------------------------
# tiny linalg — pure Python so the demo has no binary dependencies. d = 5.
# ---------------------------------------------------------------------------
def _eye(n: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _matvec(M: Sequence[Sequence[float]], v: Sequence[float]) -> List[float]:
    return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _inv(M: Sequence[Sequence[float]]) -> List[List[float]]:
    """Gauss-Jordan inverse with partial pivoting."""
    n = len(M)
    a = [list(row) + e for row, e in zip(M, _eye(n))]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            a[col][col] += 1e-9      # A is ridge-regularised, so this is rare
            piv = col
        a[col], a[piv] = a[piv], a[col]
        d = a[col][col]
        a[col] = [v / d for v in a[col]]
        for r in range(n):
            if r == col:
                continue
            f = a[r][col]
            if f:
                a[r] = [vr - f * vc for vr, vc in zip(a[r], a[col])]
    return [row[n:] for row in a]


@dataclass
class ArmState:
    name: str
    A: List[List[float]] = field(default_factory=lambda: _eye(CONTEXT_DIM))
    b: List[float] = field(default_factory=lambda: [0.0] * CONTEXT_DIM)
    pulls: int = 0
    reward_sum: float = 0.0
    fail_count: int = 0


class LinUCB:
    def __init__(self, alpha: float = 0.6, warmup: int = 4,
                 arms: Optional[List[str]] = None) -> None:
        self.alpha = alpha
        self.arms = list(arms or ARMS)
        self.state: Dict[str, ArmState] = {a: ArmState(a) for a in self.arms}
        self.t = 0
        # Round-robin warm-up. Ridge shrinkage pulls a barely-pulled arm's mean
        # towards zero, so an arm that fails its first pull can be starved by
        # the UCB bonus alone. Playing each arm `warmup` times first is the
        # standard fix and makes the live demo reproducible rather than lucky.
        self.warmup = warmup

    # ------------------------------------------------------------- selection
    def scores(self, x: Sequence[float]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for a in self.arms:
            st = self.state[a]
            Ainv = _inv(st.A)
            mean = _dot(_matvec(Ainv, st.b), x)
            bonus = self.alpha * math.sqrt(max(_dot(x, _matvec(Ainv, x)), 0.0))
            out[a] = {
                "mean": mean, "bonus": bonus, "ucb": mean + bonus,
                "pulls": st.pulls,
                "empirical": (st.reward_sum / st.pulls) if st.pulls else 0.0,
                "fail_rate": (st.fail_count / st.pulls) if st.pulls else 0.0,
            }
        return out

    def select(self, x: Sequence[float]) -> str:
        cold = [a for a in self.arms if self.state[a].pulls < self.warmup]
        if cold:
            return min(cold, key=lambda a: self.state[a].pulls)
        sc = self.scores(x)
        return max(self.arms, key=lambda a: sc[a]["ucb"])

    # ---------------------------------------------------------------- update
    def update(self, arm: str, x: Sequence[float], reward: float, did_fail: bool) -> None:
        st = self.state[arm]
        for i in range(CONTEXT_DIM):
            xi = x[i]
            if xi:
                for j in range(CONTEXT_DIM):
                    st.A[i][j] += xi * x[j]
            st.b[i] += reward * xi
        st.pulls += 1
        st.reward_sum += reward
        st.fail_count += int(did_fail)
        self.t += 1

    # ------------------------------------------------------------- reporting
    def snapshot(self, x: Sequence[float]) -> dict:
        sc = self.scores(x)
        return {
            "t": self.t,
            "alpha": self.alpha,
            "features": list(CONTEXT_FEATURES),
            "context": [round(v, 3) for v in x],
            "warming_up": any(self.state[a].pulls < self.warmup for a in self.arms),
            "arms": [
                {
                    "name": a,
                    "blurb": ARM_BLURB.get(a, ""),
                    "mean": round(sc[a]["mean"], 4),
                    "bonus": round(sc[a]["bonus"], 4),
                    "ucb": round(sc[a]["ucb"], 4),
                    "pulls": sc[a]["pulls"],
                    "empirical": round(sc[a]["empirical"], 4),
                    "fail_rate": round(sc[a]["fail_rate"], 4),
                }
                for a in self.arms
            ],
        }

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha, "warmup": self.warmup, "t": self.t,
            "arms": {
                a: {"A": self.state[a].A, "b": self.state[a].b,
                    "pulls": self.state[a].pulls,
                    "reward_sum": self.state[a].reward_sum,
                    "fail_count": self.state[a].fail_count}
                for a in self.arms
            },
        }


# ---------------------------------------------------------------------------
# online loop
# ---------------------------------------------------------------------------
@dataclass
class Tick:
    """One bandit step: one perturbed room, one arm, one reward."""
    t: int
    arm: str
    reward: float
    failed: bool
    severity: float
    culprit: str
    context: List[float]
    scene: SceneGraph


class OnlineBandit:
    """Drives a LinUCB over rooms drawn from the proposal.

    Each tick draws a fresh perturbed room from the same proposal the campaign
    uses, so the bandit is adapting to the distribution the readiness score is
    measured over — not to a separate made-up stream.
    """

    def __init__(self, scene: SceneGraph, proposal, seed: int = 0,
                 alpha: float = 0.6) -> None:
        self.scene = scene
        self.proposal = proposal
        self.rng = random.Random(seed)
        self.model = LinUCB(alpha=alpha)
        self.history: List[float] = []     # rolling reward

    def set_scene(self, scene: SceneGraph) -> None:
        """The room changed. The model is kept: arm value is a function of
        context, and the context is what just changed."""
        self.scene = scene

    def step(self) -> Tick:
        theta = self.proposal.sample(len(self.scene.items), self.rng)
        room = apply(self.scene, theta)
        x = context_vector(room)
        arm = self.model.select(x)
        reward, did_fail, severity, culprit = reward_for(room, arm)
        self.model.update(arm, x, reward, did_fail)
        self.history.append(reward)
        if len(self.history) > 400:
            self.history = self.history[-400:]
        return Tick(self.model.t, arm, reward, did_fail, severity, culprit, x, room)

    def rolling_reward(self, window: int = 25) -> float:
        h = self.history[-window:]
        return sum(h) / len(h) if h else 0.0

    def snapshot(self) -> dict:
        x = context_vector(self.scene)
        snap = self.model.snapshot(x)
        snap["rolling_reward"] = round(self.rolling_reward(), 4)
        snap["history"] = [round(v, 3) for v in self.history[-120:]]
        return snap

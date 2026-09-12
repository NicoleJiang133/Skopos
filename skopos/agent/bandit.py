"""
Contextual bandit over task strategies — LinUCB (disjoint linear model).

WHAT THIS IS AND IS NOT
-----------------------
This is a **contextual bandit**, not a trained policy. A bandit is the one-step
case of reinforcement learning: there is no state transition and no credit
assignment across time. We select one strategy per episode, observe one reward,
and update a linear value model. Nothing is "trained"; nothing is a "learned
policy". The words used throughout are *select*, *update*, *value estimate*.

WHY LinUCB RATHER THAN EPSILON-GREEDY
-------------------------------------
1. It is contextual in the way we need: the value of an arm genuinely depends on
   the room (a wide arc is worth more in a cluttered room), and LinUCB shares
   statistical strength across similar contexts via a linear model, so it
   re-orders arms within tens of episodes rather than hundreds.
2. It carries an explicit uncertainty term, alpha * sqrt(x' A^-1 x), which we
   draw on screen as the lighter part of each bar. Epsilon-greedy's exploration
   is invisible — it is just a coin flip — and makes a worse demo and a worse
   argument.
3. It is closed form and deterministic given the data, so a replay reproduces
   the exact bars.

THE MATHS
---------
Per arm a we keep A_a = I_d + sum_t x_t x_t' and b_a = sum_t r_t x_t.
Ridge solution:      theta_a = A_a^-1 b_a
UCB score:           p_a = theta_a . x + alpha * sqrt(x' A_a^-1 x)
Select argmax_a p_a, observe reward r in [0, 1], then
                     A_a += x x' ,  b_a += r x.
The identity initialisation is the ridge prior (lambda = 1), which is also what
keeps A invertible before any data arrives.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..scene_graph import CONTEXT_DIM, CONTEXT_FEATURES

ARMS: List[str] = [
    "direct_approach",
    "wide_arc",
    "slow_scan_then_approach",
    "request_human_assist",
]

ARM_BLURB: Dict[str, str] = {
    "direct_approach": "shortest path, no re-look",
    "wide_arc": "detour around flagged objects",
    "slow_scan_then_approach": "re-perceive, then move slowly",
    "request_human_assist": "stop and ask a human",
}


# ----------------------------------------------------------------- tiny linalg
# Pure Python so the demo has zero binary dependencies. d = 8; this is free.
def _eye(n: int, s: float = 1.0) -> List[List[float]]:
    return [[s if i == j else 0.0 for j in range(n)] for i in range(n)]


def _matvec(M: List[List[float]], v: List[float]) -> List[float]:
    return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _inv(M: List[List[float]]) -> List[List[float]]:
    """Gauss-Jordan inverse with partial pivoting."""
    n = len(M)
    a = [row[:] + e[:] for row, e in zip(M, _eye(n))]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            a[col][col] += 1e-9  # nudge; A is ridge-regularised so this is rare
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
    success_count: int = 0


class LinUCBBandit:
    def __init__(self, alpha: float = 0.8, arms: Optional[List[str]] = None,
                 warmup: int = 3) -> None:
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
    def scores(self, x: List[float]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for a in self.arms:
            st = self.state[a]
            Ainv = _inv(st.A)
            theta = _matvec(Ainv, st.b)
            mean = _dot(theta, x)
            var = max(_dot(x, _matvec(Ainv, x)), 0.0)
            bonus = self.alpha * math.sqrt(var)
            out[a] = {
                "mean": mean,
                "bonus": bonus,
                "ucb": mean + bonus,
                "pulls": st.pulls,
                "empirical": (st.reward_sum / st.pulls) if st.pulls else 0.0,
                "success_rate": (st.success_count / st.pulls) if st.pulls else 0.0,
            }
        return out

    def select(self, x: List[float]) -> str:
        cold = [a for a in self.arms if self.state[a].pulls < self.warmup]
        if cold:
            return min(cold, key=lambda a: self.state[a].pulls)
        sc = self.scores(x)
        return max(self.arms, key=lambda a: sc[a]["ucb"])

    # ---------------------------------------------------------------- update
    def update(self, arm: str, x: List[float], reward: float, success: bool) -> None:
        st = self.state[arm]
        for i in range(CONTEXT_DIM):
            xi = x[i]
            if xi:
                for j in range(CONTEXT_DIM):
                    st.A[i][j] += xi * x[j]
            st.b[i] += reward * xi
        st.pulls += 1
        st.reward_sum += reward
        st.success_count += int(success)
        self.t += 1

    # ------------------------------------------------------------ reporting
    def snapshot(self, x: List[float]) -> dict:
        sc = self.scores(x)
        return {
            "t": self.t,
            "alpha": self.alpha,
            "features": list(CONTEXT_FEATURES),
            "context": [round(v, 3) for v in x],
            "arms": [
                {
                    "name": a,
                    "blurb": ARM_BLURB.get(a, ""),
                    "mean": round(sc[a]["mean"], 4),
                    "bonus": round(sc[a]["bonus"], 4),
                    "ucb": round(sc[a]["ucb"], 4),
                    "pulls": sc[a]["pulls"],
                    "empirical": round(sc[a]["empirical"], 4),
                    "success_rate": round(sc[a]["success_rate"], 4),
                }
                for a in self.arms
            ],
        }

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha,
            "warmup": self.warmup,
            "t": self.t,
            "arms": {
                a: {
                    "A": self.state[a].A,
                    "b": self.state[a].b,
                    "pulls": self.state[a].pulls,
                    "reward_sum": self.state[a].reward_sum,
                    "success_count": self.state[a].success_count,
                }
                for a in self.arms
            },
        }

    @staticmethod
    def from_dict(d: dict) -> "LinUCBBandit":
        b = LinUCBBandit(alpha=d.get("alpha", 0.8), arms=list(d.get("arms", {}).keys()) or None,
                         warmup=d.get("warmup", 3))
        b.t = d.get("t", 0)
        for a, s in d.get("arms", {}).items():
            st = b.state[a]
            st.A = [row[:] for row in s["A"]]
            st.b = list(s["b"])
            st.pulls = s["pulls"]
            st.reward_sum = s["reward_sum"]
            st.success_count = s["success_count"]
        return b

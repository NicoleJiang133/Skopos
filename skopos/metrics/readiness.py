"""
Metrics: rolling success, per-hazard failure attribution, and the readiness score.

THE READINESS SCORE
-------------------
A single 0-100 number for "would I ship a robot into this room". It is a
weighted blend of four things we actually measure, and nothing else:

    R = 100 * ( 0.45 * S_w          # importance-weighted success rate
              + 0.25 * (1 - H_w)    # 1 - importance-weighted hazard-contact rate
              + 0.20 * C            # coverage: how much of the perturbation
                                    #   prior we have actually sampled (ESS-based)
              + 0.10 * T )          # timeliness: 1 - mean(time)/MAX_SECONDS

S_w and H_w are self-normalised importance-weighted estimates over sampled
perturbed rooms (see sampler/monte_carlo.py), so rare-but-severe rooms count in
proportion to their prior probability rather than to how often we drew them.

C is effective sample size over sample count, ESS/n. It is a *confidence*
discount, not an accuracy claim: a run that has only seen three rooms cannot
score above 80 no matter how well it did, which is the honest behaviour.

Bands:  READY >= 75,  MARGINAL 50-74,  NOT READY < 50.
The thresholds are a judgement call, not a result. They are stated here so they
can be argued with.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from ..agent.task import MAX_SECONDS

READY_THRESHOLD = 75.0
MARGINAL_THRESHOLD = 50.0

WEIGHTS = {"success": 0.45, "hazard": 0.25, "coverage": 0.20, "time": 0.10}

# Effective sample size at which we consider the perturbation space "covered".
COVERAGE_BUDGET_ESS = 15.0


@dataclass
class AttemptRecord:
    index: int
    arm: str
    success: bool
    reward: float
    seconds: float
    hazard_hit: Optional[str]
    hazard_object: Optional[str]
    failure_reason: Optional[str]
    weight: float = 1.0          # importance weight of the room this ran in
    severity: float = 0.0
    room: str = "base"


class MetricsStore:
    def __init__(self, window: int = 25) -> None:
        self.window = window
        self.attempts: List[AttemptRecord] = []
        self.recent: Deque[AttemptRecord] = deque(maxlen=window)
        self.sparkline: List[float] = []
        # Sum of weights, for self-normalised importance sampling.
        self._w_sum = 0.0
        self._w_sq_sum = 0.0
        self._w_success = 0.0
        self._w_hazard = 0.0
        self._t_sum = 0.0

    # --------------------------------------------------------------- ingest
    def add(self, rec: AttemptRecord) -> None:
        self.attempts.append(rec)
        self.recent.append(rec)
        w = max(rec.weight, 1e-9)
        self._w_sum += w
        self._w_sq_sum += w * w
        self._w_success += w * (1.0 if rec.success else 0.0)
        self._w_hazard += w * (1.0 if rec.hazard_hit else 0.0)
        self._t_sum += rec.seconds
        self.sparkline.append(self.rolling_success())
        if len(self.sparkline) > 400:
            self.sparkline = self.sparkline[-400:]

    # -------------------------------------------------------------- readouts
    def rolling_success(self) -> float:
        """Unweighted success over the last `window` attempts — what the operator sees."""
        if not self.recent:
            return 0.0
        return sum(1 for r in self.recent if r.success) / len(self.recent)

    def weighted_success(self) -> float:
        return (self._w_success / self._w_sum) if self._w_sum else 0.0

    def weighted_hazard_rate(self) -> float:
        return (self._w_hazard / self._w_sum) if self._w_sum else 0.0

    def ess(self) -> float:
        """Kish effective sample size: (sum w)^2 / sum w^2."""
        if self._w_sq_sum <= 0:
            return 0.0
        return (self._w_sum ** 2) / self._w_sq_sum

    def coverage(self) -> float:
        """ESS as a fraction of a 15-room reference budget, capped at 1."""
        return min(self.ess() / COVERAGE_BUDGET_ESS, 1.0)

    def mean_seconds(self) -> float:
        return (self._t_sum / len(self.attempts)) if self.attempts else 0.0

    def hazard_attribution(self) -> List[Dict[str, Any]]:
        """Which flagged object caused which failures, weighted by room weight."""
        agg: Dict[str, Dict[str, Any]] = {}
        for r in self.attempts:
            if r.success or not r.hazard_object:
                continue
            e = agg.setdefault(r.hazard_object, {
                "object_id": r.hazard_object, "flag": r.hazard_hit,
                "failures": 0, "weighted": 0.0,
            })
            e["failures"] += 1
            e["weighted"] += r.weight
        total_w = sum(e["weighted"] for e in agg.values()) or 1.0
        rows = sorted(agg.values(), key=lambda e: -e["weighted"])
        for e in rows:
            e["share"] = round(e["weighted"] / total_w, 3)
            e["weighted"] = round(e["weighted"], 3)
        return rows

    def failure_reasons(self) -> List[Dict[str, Any]]:
        agg: Dict[str, int] = {}
        for r in self.attempts:
            if r.success:
                continue
            agg[r.failure_reason or "unknown"] = agg.get(r.failure_reason or "unknown", 0) + 1
        return [{"reason": k, "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]

    # --------------------------------------------------------------- score
    def readiness(self) -> Dict[str, Any]:
        s = self.weighted_success()
        h = self.weighted_hazard_rate()
        c = self.coverage()
        t = 1.0 - min(self.mean_seconds() / MAX_SECONDS, 1.0)
        score = 100.0 * (
            WEIGHTS["success"] * s
            + WEIGHTS["hazard"] * (1.0 - h)
            + WEIGHTS["coverage"] * c
            + WEIGHTS["time"] * t
        )
        if score >= READY_THRESHOLD:
            state = "READY"
        elif score >= MARGINAL_THRESHOLD:
            state = "MARGINAL"
        else:
            state = "NOT READY"
        return {
            "score": round(score, 1),
            "state": state,
            "terms": {
                "weighted_success": round(s, 4),
                "weighted_hazard_rate": round(h, 4),
                "coverage_ess": round(c, 4),
                "timeliness": round(t, 4),
            },
            "weights": WEIGHTS,
            "ess": round(self.ess(), 2),
            "n": len(self.attempts),
            "formula": ("R = 100*(0.45*S_w + 0.25*(1-H_w) + 0.20*coverage + 0.10*timeliness); "
                        "READY>=75, MARGINAL>=50"),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rolling_success": round(self.rolling_success(), 4),
            "window": self.window,
            "n": len(self.attempts),
            "readiness": self.readiness(),
            "hazard_attribution": self.hazard_attribution(),
            "failure_reasons": self.failure_reasons(),
            "sparkline": [round(v, 4) for v in self.sparkline[-120:]],
            "mean_seconds": round(self.mean_seconds(), 2),
        }

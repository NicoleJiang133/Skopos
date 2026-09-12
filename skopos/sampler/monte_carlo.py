"""
Monte Carlo perturbation sampling with importance weighting.

THE PROBLEM
-----------
We want E_p[ failure(room) ] over the prior p on perturbed rooms. The rooms that
matter most are the rare severe ones — the dark, cluttered, mug-missing room —
and drawing from p directly spends nearly all its samples on rooms that look
like the one we scanned. Enumerating instead is not an option: the joint space
over ~10 objects x presence x pose x lighting is astronomically large.

THE FIX — IMPORTANCE SAMPLING
-----------------------------
Draw rooms from a tilted proposal q that fires the perturbation axes more often
and harder, then correct the bias with a weight:

        w(room) = p(room) / q(room)

and estimate any statistic f with the self-normalised estimator

        E_p[f]  ~=  sum_i w_i f_i / sum_i w_i .

Self-normalised (rather than the plain 1/n sum w_i f_i) because it is far lower
variance here and does not need p and q normalised — and because it is what the
readiness score wants: a weighted average, not a weighted total.

FACTORISATION
-------------
The axes are drawn independently, so both densities factorise and the weight is
a product of per-axis ratios. For axis i with activation indicator z_i and
magnitude m_i:

    z_i = 1:   w_i = [ r_i / r'_i ] * [ Beta(m_i; a_p, b_p) / Beta(m_i; a_q, b_q) ]
    z_i = 0:   w_i = (1 - r_i) / (1 - r'_i)

with r'_i = r_i^(1-tilt) >= r_i (see prior.py). Because r' >= r, an *active*
axis gets w < 1 (we over-drew it, so discount it) and an *inactive* axis gets
w > 1 (we under-drew it, so credit it). Total weight is the product over the six
axes. At tilt = 0, q == p and every weight is exactly 1.0 — worth checking on
stage, and asserted in the self-test at the bottom of this file.

VARIANCE HEALTH AND TRUNCATION
------------------------------
Importance weights can blow up: a product of six ratios has heavy tails, and we
measured raw ESS collapsing to under 1% of the sample count at high tilt. So we
use *truncated* importance sampling, clipping each weight to [0.1, 10]. This
trades a small, known bias for a large variance reduction (Ionides, 2008) and it
is a deliberate choice, not a bug — the raw weight is kept alongside the clipped
one so both are visible.

We report Kish's effective sample size ESS = (sum w)^2 / sum w^2 in the UI, and
the readiness score's coverage term is driven by it, so a run whose weights have
collapsed cannot quietly score well.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..scene_graph import Pose, SceneGraph, SceneObject
from .prior import AXES, MAG_ALPHA_P, MAG_BETA_P, PerturbationPrior


def _log_beta_pdf(x: float, a: float, b: float) -> float:
    """log Beta(x; a, b), clamped away from the endpoints."""
    x = min(max(x, 1e-6), 1.0 - 1e-6)
    log_norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    return log_norm + (a - 1.0) * math.log(x) + (b - 1.0) * math.log1p(-x)


@dataclass
class Perturbation:
    axis: str
    active: bool
    magnitude: float
    detail: str = ""

    def to_dict(self) -> dict:
        return {"axis": self.axis, "active": self.active,
                "magnitude": round(self.magnitude, 3), "detail": self.detail}


# Truncated importance sampling bounds. See the module docstring.
WEIGHT_CLIP_LO, WEIGHT_CLIP_HI = 0.1, 10.0


@dataclass
class SampledRoom:
    graph: SceneGraph
    weight: float          # truncated weight, used by every estimator
    raw_weight: float
    log_weight: float
    severity: float
    perturbations: List[Perturbation] = field(default_factory=list)
    seed: int = 0

    def to_dict(self) -> dict:
        return {
            "weight": round(self.weight, 4),
            "raw_weight": round(self.raw_weight, 4),
            "clipped": abs(self.raw_weight - self.weight) > 1e-9,
            "log_weight": round(self.log_weight, 4),
            "severity": round(self.severity, 4),
            "seed": self.seed,
            "perturbations": [p.to_dict() for p in self.perturbations],
        }


# Relative contribution of each axis to the aggregate severity that drives the
# renderer's degradation curve and the "how bad is this room" readout.
SEVERITY_WEIGHT = {
    "object_moved": 0.8,
    "object_removed": 1.3,
    "lighting": 1.0,
    "occlusion": 1.2,
    "clutter_added": 0.9,
    "reflective_surface": 0.7,
}


def draw_axes(prior: PerturbationPrior, rng: random.Random) -> Tuple[List[Perturbation], float, float]:
    """Draw one perturbation configuration from q and return it with log p - log q."""
    a_q, b_q = prior.magnitude_params_q()
    log_w = 0.0
    out: List[Perturbation] = []
    for axis in AXES:
        r = min(max(prior.rates.get(axis, 0.0), 0.0), 1.0)
        rq = prior.proposal_rate(axis)
        active = rng.random() < rq
        mag = 0.0
        if active:
            mag = rng.betavariate(a_q, b_q)
            # activation ratio
            log_w += math.log(max(r, 1e-12)) - math.log(max(rq, 1e-12))
            # magnitude ratio
            log_w += _log_beta_pdf(mag, MAG_ALPHA_P, MAG_BETA_P) - _log_beta_pdf(mag, a_q, b_q)
        else:
            log_w += math.log(max(1.0 - r, 1e-12)) - math.log(max(1.0 - rq, 1e-12))
        out.append(Perturbation(axis=axis, active=active, magnitude=mag))

    sev_num = sum(SEVERITY_WEIGHT[p.axis] * p.magnitude for p in out if p.active)
    sev_den = sum(SEVERITY_WEIGHT.values())
    severity = min(sev_num / (sev_den * 0.45), 1.0)  # 0.45 scales a typical draw to ~mid-range
    return out, log_w, severity


# --------------------------------------------------------------------- apply
CLUTTER_KINDS = [
    ("toy", "plastic", ["trip_hazard"], [0.15, 0.15, 0.12]),
    ("shoe", "fabric", ["trip_hazard"], [0.26, 0.10, 0.10]),
    ("box", "paper", ["occluding"], [0.35, 0.30, 0.28]),
    ("bottle", "glass", ["fragile", "reflective"], [0.08, 0.08, 0.25]),
    ("book stack", "paper", ["soft_unstable"], [0.20, 0.15, 0.18]),
    ("cable", "plastic", ["trip_hazard"], [0.5, 0.02, 0.01]),
]


def apply_perturbations(
    base: SceneGraph, perts: List[Perturbation], rng: random.Random
) -> SceneGraph:
    """Produce a perturbed SceneGraph. Plausible, not accurate — no physics."""
    sg = base.copy()
    sg.derived_from = base.room_id
    sg.room_id = base.room_id + "/perturbed"
    target = sg.by_label("mug")

    for p in perts:
        if not p.active or p.magnitude <= 0:
            continue
        m = p.magnitude

        if p.axis == "object_moved":
            movable = [o for o in sg.objects if o.movable]
            if movable:
                k = max(1, round(m * min(len(movable), 4)))
                moved = rng.sample(movable, min(k, len(movable)))
                for o in moved:
                    o.pose.x += rng.uniform(-1.4, 1.4) * m
                    o.pose.y += rng.uniform(-1.4, 1.4) * m
                    o.pose.yaw += rng.uniform(-1.5, 1.5) * m
                    o.confidence = max(0.2, o.confidence - 0.15 * m)
                p.detail = "moved " + ", ".join(o.id for o in moved)

        elif p.axis == "object_removed":
            movable = [o for o in sg.objects if o.movable]
            if movable:
                # High magnitude means the *target* itself can vanish. This is
                # the interesting failure and we do not hide it.
                k = max(1, round(m * 3))
                gone = rng.sample(movable, min(k, len(movable)))
                for o in gone:
                    sg.objects.remove(o)
                p.detail = "removed " + ", ".join(o.id for o in gone)

        elif p.axis == "lighting":
            sg.lighting.level = max(0.05, sg.lighting.level - 0.85 * m)
            sg.lighting.directional = sg.lighting.directional or m > 0.5
            sg.lighting.glare = min(1.0, sg.lighting.glare + 0.35 * m)
            sg.lighting.color_temp_k = int(sg.lighting.color_temp_k - 900 * m)
            p.detail = "level -> {:.2f}".format(sg.lighting.level)

        elif p.axis == "occlusion":
            if target is not None:
                tx, ty = target.pose.x, target.pose.y
            else:
                tx, ty = 1.7, 0.1
            oid = "occluder_{:03d}".format(rng.randrange(1000))
            ang = rng.uniform(0, 2 * math.pi)
            dist = 1.1 - 0.8 * m
            sg.objects.append(SceneObject(
                oid, "screen" if m > 0.5 else "chair",
                Pose(tx + dist * math.cos(ang), ty + dist * math.sin(ang), 0.0),
                [0.5 + 0.6 * m, 0.4, 1.2], material="fabric",
                hazard_flags=["occluding"], movable=True, confidence=0.7, support="floor",
            ))
            p.detail = "added {} at {:.2f} m from target".format(oid, dist)

        elif p.axis == "clutter_added":
            n = max(1, round(m * 6))
            added = []
            for _ in range(n):
                label, mat, flags, ext = rng.choice(CLUTTER_KINDS)
                oid = "clutter_{:03d}".format(rng.randrange(1000))
                sg.objects.append(SceneObject(
                    oid, label, Pose(rng.uniform(-0.4, 3.2), rng.uniform(-1.3, 1.9), 0.0),
                    list(ext), material=mat, hazard_flags=list(flags), movable=True,
                    confidence=rng.uniform(0.45, 0.85), support="floor",
                ))
                added.append(oid)
            sg.free_space_ratio = max(0.12, sg.free_space_ratio - 0.06 * n)
            p.detail = "added {} objects".format(n)

        elif p.axis == "reflective_surface":
            sg.lighting.glare = min(1.0, sg.lighting.glare + 0.5 * m)
            candidates = [o for o in sg.objects if "reflective" not in o.hazard_flags]
            k = max(1, round(m * 3))
            touched = rng.sample(candidates, min(k, len(candidates))) if candidates else []
            for o in touched:
                o.hazard_flags.append("reflective")
                o.confidence = max(0.2, o.confidence - 0.25 * m)
            p.detail = "reflective: " + ", ".join(o.id for o in touched)

    sg.perturbations = [p.to_dict() for p in perts if p.active]
    return sg


def sample_room(base: SceneGraph, prior: PerturbationPrior, rng: random.Random,
                seed: int = 0) -> SampledRoom:
    perts, log_w, severity = draw_axes(prior, rng)
    sg = apply_perturbations(base, perts, rng)
    raw = math.exp(log_w)
    w = min(max(raw, WEIGHT_CLIP_LO), WEIGHT_CLIP_HI)
    return SampledRoom(graph=sg, weight=w, raw_weight=raw, log_weight=log_w,
                       severity=severity, perturbations=perts, seed=seed)


def ess(weights: List[float]) -> float:
    """Kish effective sample size."""
    s = sum(weights)
    s2 = sum(w * w for w in weights)
    return (s * s / s2) if s2 > 0 else 0.0


def self_test(n: int = 400) -> Dict[str, Any]:
    """At tilt = 0 the proposal is the prior and every weight must be 1.0."""
    from ..perception.mock import demo_room
    rng = random.Random(0)
    p0 = PerturbationPrior.default()
    p0.tilt = 0.0
    ws = [sample_room(demo_room(), p0, rng).weight for _ in range(n)]
    max_dev = max(abs(w - 1.0) for ws_ in [ws] for w in ws_)
    p1 = PerturbationPrior.default()
    p1.tilt = 0.35
    ws1 = [sample_room(demo_room(), p1, rng).weight for _ in range(n)]
    return {
        "tilt0_max_weight_deviation": max_dev,
        "tilt0_ok": max_dev < 1e-9,
        "tilt035_mean_weight": sum(ws1) / len(ws1),
        "tilt035_ess_frac": ess(ws1) / len(ws1),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(self_test(), indent=2))

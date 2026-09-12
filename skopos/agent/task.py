"""
The one task: "fetch the mug from the table."

WHAT THIS IS
------------
A **simulated outcome model**, not a robot and not a physics engine. Given a
SceneGraph and a chosen strategy it samples an episode: a coarse 2-D path, an
optional hazard contact, a duration, and success/failure. The generative model
is hand-specified below and every coefficient is visible in this file.

Why a simulator at all: we are measuring *which rooms break a policy*, and for a
three-hour build the honest move is to make the failure model explicit and
readable rather than pretend a learned controller is executing. Swap this module
for a real rollout and nothing else in Skopos changes.

Reward (what the bandit sees), all terms in [0, 1]:

    r = success
        - 0.45 * hazard_contact
        - 0.25 * normalised_time
        - 0.30 * asked_for_help
    r = clip(r, 0, 1)

Asking a human almost always "completes" the task but is heavily discounted, so
it only wins where the other arms are genuinely unreliable — which is the
behaviour we want to show on stage.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..scene_graph import SceneGraph, SceneObject, context_vector

TARGET_LABEL = "mug"
START_XY = (-0.5, 0.25)          # doorway, room-local metres
MAX_SECONDS = 60.0

# Per-arm base competence and sensitivity to each context feature.
# Rows read: how much this feature hurts (negative) or helps (positive) the arm.
ARM_MODEL: Dict[str, Dict[str, float]] = {
    # "base" is the ceiling competence of the arm; every other coefficient is a
    # penalty (or bonus) per unit of the named context feature. Clutter,
    # darkness and free space are *centred* on a nominal room, so an ordinary
    # tidy room costs an arm almost nothing and perturbations do the damage.
    "direct_approach": {
        "base": 1.15, "occlusion": -0.80, "clutter": -0.40, "fragile_near": -0.60,
        "dark": -0.55, "glare": -0.50, "free_space": 0.30, "speed": 1.00, "help": 0.0,
    },
    "wide_arc": {
        "base": 0.95, "occlusion": -0.40, "clutter": -0.22, "fragile_near": -0.15,
        "dark": -0.45, "glare": -0.35, "free_space": 0.60, "speed": 0.62, "help": 0.0,
    },
    "slow_scan_then_approach": {
        "base": 0.90, "occlusion": -0.20, "clutter": -0.20, "fragile_near": -0.28,
        "dark": -0.18, "glare": -0.15, "free_space": 0.25, "speed": 0.38, "help": 0.0,
    },
    "request_human_assist": {
        "base": 1.05, "occlusion": -0.02, "clutter": -0.02, "fragile_near": 0.0,
        "dark": -0.02, "glare": 0.0, "free_space": 0.0, "speed": 0.30, "help": 1.0,
    },
}

# Nominal room reference points used to centre the features.
NOMINAL_CLUTTER = 0.50
NOMINAL_DARK = 0.30
NOMINAL_FREE = 0.55


@dataclass
class Episode:
    arm: str
    success: bool
    reward: float
    seconds: float
    hazard_hit: Optional[str] = None
    hazard_object: Optional[str] = None
    path: List[List[float]] = field(default_factory=list)
    p_success: float = 0.0
    context: List[float] = field(default_factory=list)
    failure_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "success": self.success,
            "reward": round(self.reward, 4),
            "seconds": round(self.seconds, 2),
            "hazard_hit": self.hazard_hit,
            "hazard_object": self.hazard_object,
            "p_success": round(self.p_success, 4),
            "failure_reason": self.failure_reason,
            "path": [[round(p[0], 3), round(p[1], 3)] for p in self.path],
        }


def _feat(sg: SceneGraph) -> Dict[str, float]:
    x = context_vector(sg, TARGET_LABEL)
    dark = 1.0 - x[1]
    return {
        "dark": dark,
        "dark_c": dark - NOMINAL_DARK,
        "glare": x[2],
        "clutter": x[3],
        "clutter_c": x[3] - NOMINAL_CLUTTER,
        "occlusion": x[4],
        "fragile_near": x[5],
        "target_present": x[6],
        "free_space": x[7],
        "free_c": x[7] - NOMINAL_FREE,
    }


def success_probability(sg: SceneGraph, arm: str) -> float:
    """Hand-specified generative model of task success. Fully visible, on purpose."""
    f = _feat(sg)
    m = ARM_MODEL[arm]
    if f["target_present"] < 0.5:
        # The mug is not in the room. Only asking a human gets anywhere.
        return 0.55 if arm == "request_human_assist" else 0.02
    score = (
        m["base"]
        + m["occlusion"] * f["occlusion"]
        + m["clutter"] * f["clutter_c"]
        + m["fragile_near"] * f["fragile_near"]
        + m["dark"] * f["dark_c"]
        + m["glare"] * f["glare"]
        + m["free_space"] * f["free_c"]
    )
    return max(0.02, min(0.985, score))


def _path_for(sg: SceneGraph, arm: str, rng: random.Random, n: int = 14) -> List[List[float]]:
    """Coarse 2-D trajectory from the doorway to the mug. Illustrative, not planned."""
    target = sg.by_label(TARGET_LABEL)
    tx, ty = (target.pose.x, target.pose.y) if target else (1.7, 0.1)
    sx, sy = START_XY
    pts: List[List[float]] = []
    # Lateral bow: the arc/scan arms swing wider around the room centre.
    bow = {"direct_approach": 0.0, "wide_arc": 0.95,
           "slow_scan_then_approach": 0.40, "request_human_assist": 0.15}[arm]
    for i in range(n + 1):
        t = i / n
        x = sx + (tx - sx) * t
        y = sy + (ty - sy) * t
        y += bow * math.sin(math.pi * t) * 1.0
        x += 0.12 * bow * math.sin(math.pi * t)
        jitter = 0.03 * (1.0 - t)
        x += rng.uniform(-jitter, jitter)
        y += rng.uniform(-jitter, jitter)
        pts.append([x, y])
    return pts


# Flags that represent something the base can physically collide with. A
# reflective surface degrades perception but you do not "hit" it, and the table
# the mug stands on is something you are *supposed* to approach.
CONTACT_FLAGS = ("fragile", "trip_hazard", "living", "soft_unstable", "spill_risk", "occluding")
# Contact with one of these ends the attempt; the rest are a cost, not a failure.
FATAL_FLAGS = ("fragile", "trip_hazard", "living")


def _box_distance(o: SceneObject, x: float, y: float) -> float:
    """Distance from a point to an object's axis-aligned footprint, 0 if inside.

    Using a bounding box rather than a radius matters: a 2 m sofa has a 1 m
    "radius" that would swallow half the room and make every path look like a
    collision.
    """
    dx = max(abs(o.pose.x - x) - o.extent[0] / 2.0, 0.0)
    dy = max(abs(o.pose.y - y) - o.extent[1] / 2.0, 0.0)
    return math.hypot(dx, dy)


def _is_floor_covering(o: SceneObject) -> bool:
    """Flat and large: a rug, not an obstacle. You drive over it."""
    return o.extent[2] < 0.05 and (o.extent[0] * o.extent[1]) > 0.5


def _nearest_hazard(
    sg: SceneGraph, xy: List[float], skip_ids: Tuple[str, ...] = ()
) -> Tuple[Optional[str], Optional[str], float]:
    """Closest collidable flagged object to a point; returns (flag, id, edge distance)."""
    best: Tuple[Optional[str], Optional[str], float] = (None, None, 1e9)
    for o in sg.objects:
        if o.id in skip_ids or o.label == TARGET_LABEL or _is_floor_covering(o):
            continue
        flags = [fl for fl in o.hazard_flags if fl in CONTACT_FLAGS]
        if not flags:
            continue
        d = _box_distance(o, xy[0], xy[1])
        if d < best[2]:
            flag = next((fl for fl in FATAL_FLAGS if fl in flags), flags[0])
            best = (flag, o.id, d)
    return best


def run_episode(sg: SceneGraph, arm: str, rng: random.Random) -> Episode:
    """Sample one attempt. `rng` is the seeded run RNG, so replays match exactly."""
    f = _feat(sg)
    m = ARM_MODEL[arm]
    p = success_probability(sg, arm)
    path = _path_for(sg, arm, rng)

    success = rng.random() < p
    hazard_flag: Optional[str] = None
    hazard_obj: Optional[str] = None
    reason: Optional[str] = None

    # Hazard contact is sampled against the closest flagged object on the path.
    # Wide arcs and slow scans keep clearance; direct approaches do not.
    clearance = {"direct_approach": 0.0, "wide_arc": 0.30,
                 "slow_scan_then_approach": 0.22, "request_human_assist": 0.45}[arm]
    target = sg.by_label(TARGET_LABEL)
    skip = tuple(i for i in [target.support if target else None] if i)
    worst_d = 1e9
    worst: Tuple[Optional[str], Optional[str]] = (None, None)
    for q in path:
        flag, oid, d = _nearest_hazard(sg, q, skip_ids=skip)
        if d < worst_d:
            worst_d, worst = d, (flag, oid)
    # Contact probability rises as the closest approach drops inside a 0.25 m
    # margin; the arm's clearance behaviour is added straight onto the distance.
    contact_p = max(0.0, min(0.85, (0.35 - (worst_d + clearance)) * 1.4))
    contact_p *= (1.0 + 0.5 * f["dark"] + 0.4 * f["glare"])
    if rng.random() < contact_p:
        hazard_flag, hazard_obj = worst
        if hazard_flag in FATAL_FLAGS:
            success = False
        reason = "hazard contact: " + str(hazard_flag)

    if not success and reason is None:
        if f["target_present"] < 0.5:
            reason = "target absent"
        elif f["occlusion"] > 0.5:
            reason = "target occluded"
        elif f["dark"] > 0.5:
            reason = "insufficient light"
        elif f["glare"] > 0.4:
            reason = "specular glare"
        else:
            reason = "grasp failed"

    # Time: inverse of the arm's speed, inflated by clutter and darkness.
    base_t = 8.0 / max(m["speed"], 0.05)
    seconds = base_t * (1.0 + 0.6 * f["clutter"] + 0.4 * f["dark"]) * rng.uniform(0.9, 1.15)
    seconds = min(seconds, MAX_SECONDS)

    reward = (1.0 if success else 0.0)
    reward -= 0.45 * (1.0 if hazard_flag else 0.0)
    reward -= 0.25 * (seconds / MAX_SECONDS)
    reward -= 0.30 * m["help"]
    reward = max(0.0, min(1.0, reward))

    return Episode(
        arm=arm, success=success, reward=reward, seconds=seconds,
        hazard_hit=hazard_flag, hazard_object=hazard_obj, path=path,
        p_success=p, context=context_vector(sg, TARGET_LABEL), failure_reason=reason,
    )

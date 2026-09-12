"""
SceneGraph — the central object of Skopos.

Everything downstream (sampler, providers, agent, metrics) depends ONLY on this
module. Pixels stop at perception; a SceneGraph is structured text and is the
only thing that ever crosses a network boundary.

HONESTY NOTE: poses are *approximate*, in metres, in a room-local frame whose
origin is the camera's first pose. There is no metric ground truth, no collision
mesh, no SLAM. This is a plausible semantic layout, not a digital twin.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "skopos.scenegraph/1"

# Hazard flags the rest of the system knows how to reason about.
HAZARD_FLAGS = (
    "fragile",         # breaks on contact (glass, ceramic)
    "reflective",      # confuses depth / vision (mirror, glossy table)
    "spill_risk",      # contains liquid
    "trip_hazard",     # low, on the floor, in a path (cable, toy)
    "occluding",       # blocks line of sight to other objects
    "soft_unstable",   # deforms under contact (rug, cushion pile)
    "living",          # pet or person — never plan through
)

MATERIALS = (
    "ceramic", "glass", "wood", "metal", "fabric", "plastic", "paper", "organic", "unknown",
)


@dataclass
class Pose:
    """Approximate position in metres, room-local frame. yaw in radians."""
    x: float
    y: float
    z: float
    yaw: float = 0.0


@dataclass
class SceneObject:
    id: str
    label: str
    pose: Pose
    extent: List[float] = field(default_factory=lambda: [0.1, 0.1, 0.1])  # approx w,d,h metres
    material: str = "unknown"
    hazard_flags: List[str] = field(default_factory=list)
    movable: bool = True
    confidence: float = 0.5          # perception confidence, 0-1
    support: Optional[str] = None    # id of the object this rests on ("floor" if none)

    def has(self, flag: str) -> bool:
        return flag in self.hazard_flags


@dataclass
class Lighting:
    """Coarse lighting descriptors. `level` 0-1 is the only thing the agent uses."""
    level: float = 0.7               # 0 = dark, 1 = bright even light
    color_temp_k: int = 4000
    directional: bool = False        # harsh single source -> hard shadows
    glare: float = 0.0               # 0-1, specular blowout


@dataclass
class SceneGraph:
    room_id: str
    objects: List[SceneObject] = field(default_factory=list)
    lighting: Lighting = field(default_factory=Lighting)
    floor_type: str = "hardwood"
    free_space_ratio: float = 0.6    # fraction of floor that is traversable (estimated)
    captured_at: float = field(default_factory=time.time)
    schema: str = SCHEMA_VERSION
    notes: str = ""

    # --- privacy accounting: these travel with the graph so the UI can show them
    frames_seen: int = 0
    frames_retained: int = 0         # MUST stay 0 unless SKOPOS_DEBUG_KEEP_FRAMES=1

    # --- provenance of this particular graph (base vs perturbed)
    derived_from: Optional[str] = None
    perturbations: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    def by_id(self, oid: str) -> Optional[SceneObject]:
        return next((o for o in self.objects if o.id == oid), None)

    def by_label(self, label: str) -> Optional[SceneObject]:
        return next((o for o in self.objects if o.label == label), None)

    def with_flag(self, flag: str) -> List[SceneObject]:
        return [o for o in self.objects if flag in o.hazard_flags]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SceneGraph":
        objs = [
            SceneObject(
                id=o["id"],
                label=o["label"],
                pose=Pose(**o["pose"]),
                extent=list(o.get("extent", [0.1, 0.1, 0.1])),
                material=o.get("material", "unknown"),
                hazard_flags=list(o.get("hazard_flags", [])),
                movable=o.get("movable", True),
                confidence=o.get("confidence", 0.5),
                support=o.get("support"),
            )
            for o in d.get("objects", [])
        ]
        sg = SceneGraph(
            room_id=d["room_id"],
            objects=objs,
            lighting=Lighting(**d.get("lighting", {})),
            floor_type=d.get("floor_type", "hardwood"),
            free_space_ratio=d.get("free_space_ratio", 0.6),
            captured_at=d.get("captured_at", time.time()),
            schema=d.get("schema", SCHEMA_VERSION),
            notes=d.get("notes", ""),
            frames_seen=d.get("frames_seen", 0),
            frames_retained=d.get("frames_retained", 0),
            derived_from=d.get("derived_from"),
            perturbations=list(d.get("perturbations", [])),
        )
        return sg

    def copy(self) -> "SceneGraph":
        return SceneGraph.from_dict(json.loads(self.to_json()))


# ---------------------------------------------------------------------------
# Context vector — the ONLY thing the bandit sees. Keep it small and readable.
# ---------------------------------------------------------------------------
CONTEXT_FEATURES = (
    "bias",            # constant 1.0
    "light_level",     # 0-1
    "glare",           # 0-1
    "clutter",         # 0-1, normalised object count in the room
    "occlusion",       # 0-1, how blocked the target is
    "fragile_near",    # 0-1, fragile mass close to the target
    "target_present",  # 1.0 if the mug is in the graph at all
    "free_space",      # 0-1
)
CONTEXT_DIM = len(CONTEXT_FEATURES)


def context_vector(sg: SceneGraph, target_label: str = "mug") -> List[float]:
    """Map a SceneGraph to a fixed-length, human-readable feature vector.

    Deliberately hand-specified and small: with 4 arms and a couple of hundred
    demo attempts, a learned encoder would be noise. Every feature is something
    a judge can point at on screen and trace to the JSON.
    """
    target = sg.by_label(target_label)
    # Clutter: object count against a 20-object reference room.
    clutter = min(len(sg.objects) / 20.0, 1.0)

    # Proximity kernels. A Gaussian with sigma = 0.6 m: an object half a metre
    # from the mug contributes most of its weight, one two metres away almost
    # none. Divided by 4.0 so a normal room with a couple of nearby flagged
    # objects lands around 0.2-0.3 rather than saturating at 1.0.
    SIGMA2 = 2 * 0.6 ** 2
    NORM = 4.0

    def _prox(objs, tx, ty, skip_id=None):
        acc = 0.0
        for o in objs:
            if o.id == skip_id:
                continue
            d2 = (o.pose.x - tx) ** 2 + (o.pose.y - ty) ** 2
            acc += math.exp(-d2 / SIGMA2)
        return min(acc / NORM, 1.0)

    if target is None:
        occlusion = 1.0
        fragile_near = 0.0
    else:
        tx, ty = target.pose.x, target.pose.y
        occlusion = _prox(sg.with_flag("occluding"), tx, ty)
        fragile_near = _prox(sg.with_flag("fragile"), tx, ty, skip_id=target.id)

    return [
        1.0,
        float(sg.lighting.level),
        float(sg.lighting.glare),
        clutter,
        occlusion,
        fragile_near,
        1.0 if target is not None else 0.0,
        float(sg.free_space_ratio),
    ]

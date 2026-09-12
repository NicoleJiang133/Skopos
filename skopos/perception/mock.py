"""
Mock perception — a hand-written SceneGraph for the demo room.

This is the zero-API-key path and the one used on stage. It is a *hand-authored*
room: no vision model ran. Labelled as such in the graph notes so nobody can
mistake it for a real scan.
"""
from __future__ import annotations

from typing import List, Optional

from ..privacy import PrivacyLedger
from ..scene_graph import Lighting, Pose, SceneGraph, SceneObject
from .base import PerceptionBackend


def demo_room(room_id: str = "demo-living-room") -> SceneGraph:
    """A small living room, ~4m x 3m, camera origin at the doorway."""
    objs = [
        SceneObject("table_01", "table", Pose(1.8, 0.2, 0.0), [1.2, 0.8, 0.74],
                    material="wood", hazard_flags=["reflective"], movable=False,
                    confidence=0.94, support="floor"),
        SceneObject("mug_01", "mug", Pose(1.7, 0.1, 0.78), [0.09, 0.09, 0.10],
                    material="ceramic", hazard_flags=["fragile", "spill_risk"],
                    movable=True, confidence=0.88, support="table_01"),
        SceneObject("laptop_01", "laptop", Pose(2.32, 0.48, 0.76), [0.32, 0.22, 0.02],
                    material="metal", hazard_flags=["fragile", "reflective"],
                    movable=True, confidence=0.91, support="table_01"),
        SceneObject("chair_01", "chair", Pose(1.3, -0.5, 0.0), [0.45, 0.45, 0.9],
                    material="wood", hazard_flags=["occluding"], movable=True,
                    confidence=0.9, support="floor"),
        SceneObject("sofa_01", "sofa", Pose(0.4, 1.5, 0.0), [2.0, 0.9, 0.8],
                    material="fabric", hazard_flags=["occluding", "soft_unstable"],
                    movable=False, confidence=0.96, support="floor"),
        SceneObject("rug_01", "rug", Pose(1.2, 0.6, 0.0), [1.8, 1.2, 0.01],
                    material="fabric", hazard_flags=["soft_unstable", "trip_hazard"],
                    movable=False, confidence=0.83, support="floor"),
        SceneObject("cable_01", "cable", Pose(0.9, -0.2, 0.0), [0.6, 0.02, 0.01],
                    material="plastic", hazard_flags=["trip_hazard"], movable=True,
                    confidence=0.61, support="floor"),
        SceneObject("lamp_01", "floor lamp", Pose(2.6, 1.1, 0.0), [0.3, 0.3, 1.6],
                    material="metal", hazard_flags=["fragile"], movable=True,
                    confidence=0.87, support="floor"),
        SceneObject("plant_01", "potted plant", Pose(2.9, -0.4, 0.0), [0.4, 0.4, 0.7],
                    material="organic", hazard_flags=["fragile", "occluding"],
                    movable=True, confidence=0.79, support="floor"),
        SceneObject("tv_01", "television", Pose(0.2, -1.0, 0.6), [1.1, 0.06, 0.65],
                    material="glass", hazard_flags=["fragile", "reflective"],
                    movable=False, confidence=0.93, support="floor"),
    ]
    return SceneGraph(
        room_id=room_id,
        objects=objs,
        lighting=Lighting(level=0.72, color_temp_k=3800, directional=True, glare=0.12),
        floor_type="hardwood",
        free_space_ratio=0.58,
        notes=("hand-authored demo room; no vision model was run. "
               "Poses are approximate and have no metric ground truth."),
    )


class MockPerception(PerceptionBackend):
    name = "mock"

    def scene_from_frames(
        self,
        frames: List[bytes],
        ledger: Optional[PrivacyLedger] = None,
        room_id: str = "demo-living-room",
    ) -> SceneGraph:
        n = len(frames)
        if ledger is not None:
            ledger.note_frames(n)
        # `frames` goes out of scope here. Nothing is written.
        del frames
        sg = demo_room(room_id)
        if ledger is not None:
            sg.frames_seen = ledger.frames_seen
            sg.frames_retained = ledger.frames_retained
        return sg

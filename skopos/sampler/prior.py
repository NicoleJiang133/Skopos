"""
The perturbation prior: six named axes over which a real room differs from the
room you scanned.

We never enumerate the product space of object states. There are ~10 objects,
each with position / presence / material variation, plus lighting — the joint
space is astronomically large and enumerating it is both impossible and
pointless. Instead each axis carries a *rate* (how often that kind of change
happens) and a *magnitude* distribution (how big it is when it does), and we
draw rooms from the resulting product measure by Monte Carlo.

Rates are the numbers behind the six sliders in the UI. They are priors, i.e.
assumptions, not measurements — stated as such in the README.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List

AXES: List[str] = [
    "object_moved",
    "object_removed",
    "lighting",
    "occlusion",
    "clutter_added",
    "reflective_surface",
]

AXIS_DESC: Dict[str, str] = {
    "object_moved": "something is not where you left it",
    "object_removed": "something is gone entirely (including the mug)",
    "lighting": "darker, or lit from a harsher angle",
    "occlusion": "the line of sight to the target is blocked",
    "clutter_added": "new objects on the floor and surfaces",
    "reflective_surface": "mirrors, glass, glossy finishes",
}

# Default rates: how likely each axis is to be active in a room drawn from the
# prior. Hand-set from "what actually changes in a living room day to day".
DEFAULT_RATES: Dict[str, float] = {
    "object_moved": 0.55,
    "object_removed": 0.20,
    "lighting": 0.45,
    "occlusion": 0.30,
    "clutter_added": 0.35,
    "reflective_surface": 0.15,
}

# Magnitude prior: Beta(2, 5), mean 2/7 ~= 0.29. Most changes are small.
MAG_ALPHA_P = 2.0
MAG_BETA_P = 5.0


@dataclass
class PerturbationPrior:
    rates: Dict[str, float]
    # Importance-sampling tilt, 0 = sample straight from the prior (all weights
    # exactly 1), 1 = aggressively oversample severe rooms.
    tilt: float = 0.3

    @staticmethod
    def default() -> "PerturbationPrior":
        return PerturbationPrior(rates=dict(DEFAULT_RATES))

    def proposal_rate(self, axis: str) -> float:
        """q's activation rate for an axis: r^(1 - tilt).

        r^(1-tilt) >= r for r in [0,1], so raising the tilt makes every axis more
        likely to fire under the proposal. At tilt = 0 it is exactly r and the
        proposal collapses onto the prior.
        """
        r = min(max(self.rates.get(axis, 0.0), 0.0), 1.0)
        if r <= 0.0:
            return 0.0
        if r >= 1.0:
            return 1.0
        return r ** (1.0 - min(max(self.tilt, 0.0), 1.0))

    def magnitude_params_q(self) -> tuple:
        """Beta(2 + 3*tilt, 5 - 3*tilt): shifts mass towards large magnitudes."""
        t = min(max(self.tilt, 0.0), 1.0)
        return (MAG_ALPHA_P + 3.0 * t, MAG_BETA_P - 3.0 * t)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["axes"] = AXES
        d["descriptions"] = AXIS_DESC
        d["magnitude_prior"] = {"alpha": MAG_ALPHA_P, "beta": MAG_BETA_P}
        d["magnitude_proposal"] = dict(zip(("alpha", "beta"), self.magnitude_params_q()))
        return d

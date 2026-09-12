"""
SKOPOS — perturbation sampling engine.

Stdlib only. No API calls. No dependencies. This is deliberate: every rendered
frame costs a world-model call, so scoring happens on the scene graph and only a
handful of elite samples are ever rendered.

Three tiers:
  1. surrogate  — geometric/semantic failure score, microseconds per sample
  2. baseline   — Monte Carlo estimate of P(failure) under a prior
  3. search     — cross-entropy method, a tractable stand-in for adaptive
                  stress testing, to find rare-but-plausible failures

Plus importance re-weighting: sample ONCE, score under many priors for free.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Callable, Sequence

# --------------------------------------------------------------------------
# scene graph
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One object in the room. Positions in metres, room-local."""

    name: str
    x: float
    y: float
    radius: float = 0.2
    reflective: bool = False   # glass / mirror / polished -> depth sensor hazard
    low_contrast: bool = False  # black rug -> reads as a hole
    movable: bool = True
    present: bool = True


@dataclass(frozen=True)
class SceneGraph:
    """What leaves the device. Structured text only, never pixels."""

    items: tuple[Item, ...]
    robot: tuple[float, float] = (0.0, 0.0)
    target: str = "mug"
    lighting: float = 1.0       # 0 dark .. 1 bright
    clutter: int = 0            # extra unmodelled obstacles

    def get(self, name: str) -> Item | None:
        for it in self.items:
            if it.name == name and it.present:
                return it
        return None


# --------------------------------------------------------------------------
# perturbation vector + prior
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Theta:
    """A sampled perturbation of the base scene. Continuous, never enumerated."""

    offsets: tuple[tuple[float, float], ...]  # per-item (dx, dy)
    removed: tuple[bool, ...]                 # per-item presence flip
    lighting: float
    clutter: int


@dataclass(frozen=True)
class Prior:
    """
    A home archetype. Defines the distribution perturbations are drawn from,
    so the same samples can be re-scored under any archetype for free.
    """

    name: str
    move_sigma: float       # metres of positional drift, per item
    remove_p: float         # chance an item is absent
    light_mean: float
    light_sigma: float
    clutter_lambda: float   # Poisson mean for unmodelled obstacles

    # -- sampling ---------------------------------------------------------

    def sample(self, n_items: int, rng: random.Random) -> Theta:
        return Theta(
            offsets=tuple(
                (rng.gauss(0.0, self.move_sigma), rng.gauss(0.0, self.move_sigma))
                for _ in range(n_items)
            ),
            removed=tuple(rng.random() < self.remove_p for _ in range(n_items)),
            lighting=_clamp(rng.gauss(self.light_mean, self.light_sigma), 0.0, 1.0),
            clutter=_poisson(self.clutter_lambda, rng),
        )

    # -- density ----------------------------------------------------------

    def log_pdf(self, theta: Theta) -> float:
        """log p(theta). Used for importance weights and for AST plausibility."""
        lp = 0.0
        for (dx, dy) in theta.offsets:
            lp += _log_normal(dx, 0.0, self.move_sigma)
            lp += _log_normal(dy, 0.0, self.move_sigma)
        for gone in theta.removed:
            lp += math.log(self.remove_p if gone else 1.0 - self.remove_p)
        lp += _log_normal(theta.lighting, self.light_mean, self.light_sigma)
        lp += _log_poisson(theta.clutter, self.clutter_lambda)
        return lp


ARCHETYPES = {
    "minimalist": Prior("minimalist", 0.19, 0.05, 0.78, 0.24, 1.0),
    "typical_flat": Prior("typical_flat", 0.22, 0.07, 0.66, 0.20, 2.0),
    "family_home": Prior("family_home", 0.32, 0.12, 0.58, 0.24, 4.0),
}

# Defensive proposal: deliberately over-dispersed relative to EVERY archetype,
# so importance weights stay bounded when we re-score. Sampling from a narrow
# proposal and re-weighting to a wide target is what collapses effective sample
# size — in high dimensions the weights degenerate onto a handful of samples.
# Always sample from this; never from an archetype directly.
DEFENSIVE = Prior("defensive", 0.46, 0.15, 0.68, 0.36, 3.2)


@dataclass(frozen=True)
class MixtureProposal:
    """
    Defensive mixture proposal:  q(x) = (1/K) * sum_k p_k(x)

    Sampling from any single archetype and re-weighting to another makes the
    weight ratio unbounded, and in ~15 dimensions the effective sample size
    collapses onto a handful of draws. Mixing every target archetype (plus one
    deliberately over-dispersed component) into the proposal bounds the ratio:

        p_i(x) / q(x)  <=  K   for every target i

    which floors the effective sample size at roughly M/K. This is the standard
    defensive importance sampling construction and it is what makes re-scoring
    under several archetypes from ONE campaign statistically honest.
    """

    components: tuple[Prior, ...]

    @property
    def name(self) -> str:
        return "mixture[" + ",".join(c.name for c in self.components) + "]"

    def sample(self, n_items: int, rng: random.Random) -> Theta:
        return rng.choice(self.components).sample(n_items, rng)

    def log_pdf(self, theta: Theta) -> float:
        lps = [c.log_pdf(theta) for c in self.components]
        mx = max(lps)
        return mx + math.log(sum(math.exp(lp - mx) for lp in lps)) - math.log(len(lps))


def default_proposal() -> MixtureProposal:
    return MixtureProposal(tuple(ARCHETYPES.values()) + (DEFENSIVE,))


def apply(scene: SceneGraph, theta: Theta) -> SceneGraph:
    items = []
    for it, (dx, dy), gone in zip(scene.items, theta.offsets, theta.removed):
        if not it.movable:
            items.append(it)
            continue
        items.append(replace(it, x=it.x + dx, y=it.y + dy, present=it.present and not gone))
    return replace(
        scene, items=tuple(items), lighting=theta.lighting, clutter=theta.clutter
    )


# --------------------------------------------------------------------------
# tier 1: surrogate score — no rendering, no network
# --------------------------------------------------------------------------

W_TASK, W_HAZARD, W_TIME = 1.0, 2.5, 0.25
FAIL_THRESHOLD = 1.0

# Hazard contact dominates: a robot cracking a glass table is far worse than a
# slow or failed fetch. Two distinct hazard kinds, which is the modelling point:
#   COLLISION  — the robot physically hits something. Geometry.
#   PERCEPTION — the sensor misreads a surface (glass invisible to LiDAR, a dark
#                rug read as a drop). Only bites when the robot can't see well,
#                so it scales with darkness and is recoverable by scanning.


def surrogate(scene: SceneGraph, strategy: str = "direct_approach") -> tuple[float, str]:
    """
    Severity score for one configuration. Returns (severity, attribution).
    Higher is worse. >= FAIL_THRESHOLD counts as a failure.
    """
    target = scene.get(scene.target)
    if target is None:
        return W_TASK * 1.5, "target_absent"

    rx, ry = scene.robot
    tx, ty = target.x, target.y
    path_len = math.hypot(tx - rx, ty - ry)

    clearance = {
        "direct_approach": 0.00,
        "wide_arc": 0.30,
        "slow_scan_then_approach": 0.12,
        "request_human_assist": 0.55,
    }.get(strategy, 0.0)
    time_cost = {
        "direct_approach": 0.0,
        "wide_arc": 0.4,
        "slow_scan_then_approach": 0.7,
        "request_human_assist": 1.6,
    }.get(strategy, 0.0)
    # scanning and asking for help both buy sensing confidence
    sensing = {
        "direct_approach": 0.0,
        "wide_arc": 0.15,
        "slow_scan_then_approach": 0.70,
        "request_human_assist": 0.90,
    }.get(strategy, 0.0)

    dark = _clamp((0.55 - scene.lighting) / 0.55, 0.0, 1.0)  # 0 bright .. 1 pitch

    hazard, culprit = 0.0, "none"
    for it in scene.items:
        if not it.present or it.name == scene.target:
            continue
        d = _point_segment_distance(it.x, it.y, rx, ry, tx, ty)

        # collision: only when the robot's swept path actually intersects
        gap = (d + clearance) - it.radius
        if gap < 0:
            sev = 0.9 * (-gap)
            if sev > hazard:
                hazard, culprit = sev, it.name

        # perception: sensor-hostile surfaces near the path, darkness-gated
        if (it.reflective or it.low_contrast) and d < it.radius + 0.5:
            mis = (1.6 if it.reflective else 1.1) * dark * (1.0 - sensing)
            if mis > hazard:
                hazard, culprit = mis, it.name

    # unmodelled clutter: obstacles that simply weren't in the scan
    clutter_risk = 0.055 * scene.clutter * (1.0 - 0.6 * clearance)
    if clutter_risk > hazard:
        hazard, culprit = clutter_risk, "unmodelled_clutter"

    # the fetch itself fails if it's too dark to identify the target
    task_fail = max(0.0, dark - 0.55) * 2.4 * (1.0 - sensing)

    severity = W_TASK * task_fail + W_HAZARD * hazard + W_TIME * (time_cost + 0.1 * path_len)
    if culprit == "none" and task_fail > 0:
        culprit = "low_light"
    return severity, culprit


def failed(sev: float) -> bool:
    return sev >= FAIL_THRESHOLD


# --------------------------------------------------------------------------
# tier 2: Monte Carlo baseline + importance re-weighting
# --------------------------------------------------------------------------


@dataclass
class Campaign:
    """One sampling campaign. Sample once, re-score under any prior for free."""

    scene: SceneGraph
    proposal: Prior | MixtureProposal
    thetas: list[Theta] = field(default_factory=list)
    severities: list[float] = field(default_factory=list)
    culprits: list[str] = field(default_factory=list)

    def run(self, m: int, strategy: str = "direct_approach", seed: int = 0) -> "Campaign":
        rng = random.Random(seed)
        n = len(self.scene.items)
        for _ in range(m):
            th = self.proposal.sample(n, rng)
            sev, who = surrogate(apply(self.scene, th), strategy)
            self.thetas.append(th)
            self.severities.append(sev)
            self.culprits.append(who)
        return self

    # -- estimates --------------------------------------------------------

    def p_fail(self) -> float:
        """Plain MC estimate under the proposal prior."""
        if not self.severities:
            return 0.0
        return sum(failed(s) for s in self.severities) / len(self.severities)

    def p_fail_under(self, prior: Prior) -> tuple[float, float]:
        """
        Self-normalised importance sampling:

            P_i(fail) ~= sum_m w_m * 1(fail_m) / sum_m w_m ,
            w_m = p_i(theta_m) / q(theta_m)

        Returns (estimate, effective_sample_size). ESS degrades as the target
        prior moves away from the proposal — report it, never hide it.
        """
        if not self.thetas:
            return 0.0, 0.0
        logw = [prior.log_pdf(t) - self.proposal.log_pdf(t) for t in self.thetas]
        mx = max(logw)
        w = [math.exp(lw - mx) for lw in logw]  # stabilised
        sw = sum(w)
        if sw <= 0:
            return 0.0, 0.0
        est = sum(wi for wi, s in zip(w, self.severities) if failed(s)) / sw
        ess = (sw ** 2) / sum(wi * wi for wi in w)
        return est, ess

    def attribution(self) -> dict[str, int]:
        """Which object is responsible for failures. Drives the hazard list."""
        out: dict[str, int] = {}
        for s, c in zip(self.severities, self.culprits):
            if failed(s):
                out[c] = out.get(c, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def readiness(self) -> tuple[int, str]:
        p = self.p_fail()
        score = int(round(100 * (1.0 - p)))
        state = "READY" if score >= 85 else "MARGINAL" if score >= 60 else "NOT READY"
        return score, state

    def elite(self, k: int) -> list[Theta]:
        """Worst k configurations — the only ones worth spending a render on."""
        order = sorted(range(len(self.thetas)), key=lambda i: -self.severities[i])
        return [self.thetas[i] for i in order[:k]]


# --------------------------------------------------------------------------
# tier 3: cross-entropy method — tractable adaptive stress testing
# --------------------------------------------------------------------------


@dataclass
class CEMResult:
    iterations: list[float]          # failure rate per iteration
    final_proposal: Prior
    worst: list[tuple[float, Theta]]


def cem_search(
    scene: SceneGraph,
    start: Prior,
    strategy: str = "direct_approach",
    batch: int = 400,
    elite_frac: float = 0.1,
    iters: int = 5,
    seed: int = 0,
    plausibility: Prior | None = None,
    lam: float = 0.60,
    alpha: float = 0.45,
) -> CEMResult:
    """
    Iteratively refit the sampling distribution to its own worst outcomes.

    This is a stand-in for full adaptive stress testing (which needs an MCTS or
    RL solver we have no time to train). It keeps AST's key idea: penalise
    severity by implausibility via `lam * -log p(theta)`, so the search finds
    failures that could ACTUALLY HAPPEN rather than absurd configurations.
    """
    rng = random.Random(seed)
    q = start
    ref = plausibility or start
    n = len(scene.items)
    history: list[float] = []
    worst: list[tuple[float, Theta]] = []

    for _ in range(iters):
        pool: list[tuple[float, float, Theta]] = []  # (objective, raw sev, theta)
        for _ in range(batch):
            th = q.sample(n, rng)
            sev, _ = surrogate(apply(scene, th), strategy)
            obj = sev + lam * ref.log_pdf(th) / max(1, n)  # reward plausibility
            pool.append((obj, sev, th))

        history.append(sum(1 for _, s, _ in pool if failed(s)) / batch)
        pool.sort(key=lambda r: -r[0])
        keep = pool[: max(2, int(elite_frac * batch))]
        worst = [(s, t) for _, s, t in keep[:5]]

        # refit: moment-match the elite set
        ths = [t for _, _, t in keep]
        drift = [d for t in ths for off in t.offsets for d in off]
        # smoothed update: blend toward the elite fit rather than jumping to
        # it, so the search converges over several visible iterations
        def mix(old: float, new: float) -> float:
            return (1 - alpha) * old + alpha * new

        q = Prior(
            name=f"{q.name}*",
            move_sigma=max(0.02, mix(q.move_sigma, _std(drift))),
            remove_p=_clamp(mix(q.remove_p, _mean([sum(t.removed) / n for t in ths])), 0.01, 0.9),
            light_mean=_clamp(mix(q.light_mean, _mean([t.lighting for t in ths])), 0.0, 1.0),
            light_sigma=max(0.03, mix(q.light_sigma, _std([t.lighting for t in ths]))),
            clutter_lambda=max(0.1, mix(q.clutter_lambda, _mean([t.clutter for t in ths]))),
        )

    return CEMResult(history, q, worst)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


ESS_MIN = 200.0


def reliable(ess: float) -> bool:
    """
    An importance-weighted estimate is only as good as its effective sample
    size. Below this the weights have degenerated onto a few samples and the
    number is noise — the UI must grey it out rather than show it.
    """
    return ess >= ESS_MIN


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _log_normal(x: float, mu: float, sigma: float) -> float:
    sigma = max(sigma, 1e-6)
    return -0.5 * math.log(2 * math.pi * sigma * sigma) - ((x - mu) ** 2) / (2 * sigma * sigma)


def _log_poisson(k: int, lam: float) -> float:
    lam = max(lam, 1e-6)
    return k * math.log(lam) - lam - math.lgamma(k + 1)


def _poisson(lam: float, rng: random.Random) -> int:
    if lam <= 0:
        return 0
    ell, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= ell:
            return k
        k += 1


def _point_segment_distance(px, py, ax, ay, bx, by) -> float:
    vx, vy = bx - ax, by - ay
    denom = vx * vx + vy * vy
    if denom < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = _clamp(((px - ax) * vx + (py - ay) * vy) / denom, 0.0, 1.0)
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


# --------------------------------------------------------------------------
# demo room
# --------------------------------------------------------------------------

DEMO_ROOM = SceneGraph(
    items=(
        Item("mug", 2.4, 1.1, 0.06),
        Item("glass_table", 1.6, 0.9, 0.45, reflective=True),
        Item("dark_rug", 1.35, 0.85, 0.45, low_contrast=True, movable=False),
        Item("sofa", 0.6, 2.0, 0.70, movable=False),
        Item("floor_lamp", 2.9, 2.1, 0.18),
        Item("cable_coil", 1.9, 0.3, 0.15),
    ),
    robot=(0.0, 0.0),
    target="mug",
)

STRATEGIES = (
    "direct_approach",
    "wide_arc",
    "slow_scan_then_approach",
    "request_human_assist",
)

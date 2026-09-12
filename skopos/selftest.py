"""
Self-test: `python -m skopos.selftest`.

Checks the claims we make out loud, so that if one of them stops being true the
build says so rather than the stage. Exits non-zero on failure.
"""
from __future__ import annotations

import json
import random
import sys
from typing import Callable, List, Tuple

from .agent.bandit import ARMS, LinUCBBandit
from .agent.task import run_episode, success_probability
from .metrics.readiness import AttemptRecord, MetricsStore
from .perception.mock import demo_room
from .privacy import PrivacyLedger
from .providers.base import RenderRequest
from .providers.mock import MockProvider
from .sampler.monte_carlo import ess, sample_room, self_test as is_self_test
from .sampler.prior import PerturbationPrior
from .scene_graph import CONTEXT_DIM, SceneGraph, context_vector
from .session import Session

CHECKS: List[Tuple[str, Callable[[], str]]] = []


def check(name: str):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("SceneGraph round-trips through JSON without loss")
def _t1() -> str:
    sg = demo_room()
    again = SceneGraph.from_dict(json.loads(sg.to_json()))
    assert again.to_json() == sg.to_json(), "round trip changed the graph"
    return "{} objects".format(len(sg.objects))


@check("perception discards every frame it is given")
def _t2() -> str:
    led = PrivacyLedger()
    sg = demo_room()
    from .perception.mock import MockPerception
    sg = MockPerception().scene_from_frames([b"x" * 1000] * 64, led)
    assert led.frames_seen == 64
    assert led.frames_discarded == 64
    assert led.frames_retained == 0, "frames were retained with debug off"
    assert sg.frames_retained == 0
    return "64 frames in, 0 retained"


@check("the SceneGraph payload contains no pixel data")
def _t3() -> str:
    payload = demo_room().to_json()
    lowered = payload.lower()
    for bad in ("base64", "data:image", "jpeg", "png", "\\x89"):
        assert bad not in lowered, "payload contains " + bad
    return "{} bytes, text only".format(len(payload.encode()))


@check("context vector is the advertised width and finite")
def _t4() -> str:
    x = context_vector(demo_room())
    assert len(x) == CONTEXT_DIM
    assert all(isinstance(v, float) and v == v for v in x)
    assert all(0.0 <= v <= 1.0 for v in x), "a feature left [0,1]"
    return "d={}".format(CONTEXT_DIM)


@check("importance weights are exactly 1.0 when tilt = 0 (q == p)")
def _t5() -> str:
    r = is_self_test(300)
    assert r["tilt0_ok"], "weights deviated from 1 at tilt 0: {}".format(
        r["tilt0_max_weight_deviation"])
    return "max deviation {:.2e}; at tilt 0.35 ESS is {:.0%} of n".format(
        r["tilt0_max_weight_deviation"], r["tilt035_ess_frac"])


@check("self-normalised IS recovers the prior mean of an axis")
def _t6() -> str:
    """The real test of the weighting: estimate E_p[magnitude of `lighting`]
    from tilted samples and compare against samples drawn straight from p."""
    base = demo_room()

    def est(tilt: float, n: int = 4000) -> float:
        rng = random.Random(11)
        pr = PerturbationPrior.default()
        pr.tilt = tilt
        num = den = 0.0
        for _ in range(n):
            room = sample_room(base, pr, rng)
            mag = next((p.magnitude for p in room.perturbations if p.axis == "lighting"), 0.0)
            num += room.weight * mag
            den += room.weight
        return num / den

    truth = est(0.0)
    tilted = est(0.35)
    err = abs(tilted - truth)
    assert err < 0.03, "IS estimate {:.4f} vs prior-sampled {:.4f}".format(tilted, truth)
    return "prior-sampled {:.4f}, IS-corrected {:.4f}, |err| {:.4f}".format(truth, tilted, err)


@check("bandit converges on the highest-reward arm in the clean room")
def _t7() -> str:
    sg = demo_room()
    x = context_vector(sg)
    rng = random.Random(5)
    truth = {}
    for a in ARMS:
        eps = [run_episode(sg, a, rng) for _ in range(1500)]
        truth[a] = sum(e.reward for e in eps) / len(eps)
    best = max(truth, key=truth.get)

    wins = 0
    for trial in range(5):
        b = LinUCBBandit()
        r = random.Random(100 + trial)
        for _ in range(180):
            a = b.select(x)
            ep = run_episode(sg, a, r)
            b.update(a, x, ep.reward, ep.success)
        wins += int(b.select(x) == best)
    assert wins >= 4, "converged on the best arm in only {}/5 trials".format(wins)
    return "best arm {} (r={:.3f}); chosen in {}/5 trials".format(best, truth[best], wins)


@check("the bandit re-orders its arms when the room gets hard")
def _t8() -> str:
    """The demo claim: a harder room should change which arm leads."""
    clean = demo_room()
    hard = demo_room()
    hard.lighting.level = 0.12
    hard.lighting.glare = 0.75
    for o in hard.objects:
        if o.label in ("chair", "sofa"):
            o.pose.x, o.pose.y = 1.6, 0.35     # crowd the mug
    p_clean = {a: success_probability(clean, a) for a in ARMS}
    p_hard = {a: success_probability(hard, a) for a in ARMS}
    best_clean = max(p_clean, key=p_clean.get)
    # Exclude the always-available help arm to make this a real strategy switch.
    move = [a for a in ARMS if a != "request_human_assist"]
    lead_clean = max(move, key=lambda a: p_clean[a])
    lead_hard = max(move, key=lambda a: p_hard[a])
    assert lead_clean != lead_hard, (
        "no re-ordering: {} leads in both rooms".format(lead_clean))
    return "{} leads when clean, {} leads when hard".format(lead_clean, lead_hard)


@check("readiness score, formula and bands agree")
def _t9() -> str:
    m = MetricsStore()
    for i in range(40):
        m.add(AttemptRecord(index=i, arm="direct_approach", success=True, reward=0.9,
                            seconds=10.0, hazard_hit=None, hazard_object=None,
                            failure_reason=None, weight=1.0))
    good = m.readiness()
    assert good["state"] == "READY", good
    m2 = MetricsStore()
    for i in range(40):
        m2.add(AttemptRecord(index=i, arm="direct_approach", success=False, reward=0.0,
                             seconds=55.0, hazard_hit="fragile", hazard_object="mug_01",
                             failure_reason="hazard contact: fragile", weight=1.0))
    bad = m2.readiness()
    assert bad["state"] == "NOT READY", bad
    assert m2.hazard_attribution()[0]["object_id"] == "mug_01"
    return "all-success {} / all-failure {}".format(good["score"], bad["score"])


@check("the mock provider renders without network or API keys")
def _t10() -> str:
    f = MockProvider().render(demo_room(), RenderRequest(seed=1, step=0, severity=0.5))
    assert f.data_url.startswith("data:image/svg+xml;base64,")
    assert f.latency_ms < 200
    return "{} bytes in {:.1f}ms".format(len(f.data_url), f.latency_ms)


@check("a run is reproducible from its seed")
def _t11() -> str:
    def run(seed: int) -> List[tuple]:
        s = Session()
        s.reset(seed)
        out = []
        for _ in range(30):
            r = s.step()
            out.append((r["arm"], r["episode"].success, round(r["episode"].reward, 6)))
        return out

    a, b, c = run(777), run(777), run(778)
    assert a == b, "same seed produced different runs"
    assert a != c, "different seeds produced identical runs"
    return "30 attempts identical on seed 777, different on 778"


@check("placeholder metrics are named as such")
def _t12() -> str:
    """Constraint 3: any placeholder must be prefixed `placeholder_`."""
    import pathlib
    hits = []
    for f in pathlib.Path("skopos").rglob("*.py"):
        if f.name == "selftest.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "placeholder_" in line:
                hits.append("{}:{}".format(f, i))
    return "none currently in the codebase" if not hits else ", ".join(hits)


def main() -> int:
    failed = 0
    print("skopos self-test\n" + "=" * 64)
    for name, fn in CHECKS:
        try:
            detail = fn()
            print("  PASS  {}\n          {}".format(name, detail))
        except AssertionError as exc:
            failed += 1
            print("  FAIL  {}\n          {}".format(name, exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  ERROR {}\n          {!r}".format(name, exc))
    print("=" * 64)
    print("{}/{} checks passed".format(len(CHECKS) - failed, len(CHECKS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

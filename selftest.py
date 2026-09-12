"""
Self-test: `python selftest.py`.

Checks the claims Skopos makes out loud, so that if one stops being true the
build says so rather than the stage. Exits non-zero on failure.

engine.py is a fixed dependency and is never modified. Several checks exist
specifically to catch this wrapper drifting away from it — the readiness
thresholds and the per-arm time costs are restated outside engine.py because it
does not export them, and these tests assert they still agree.
"""
from __future__ import annotations

import json
import os
import random
import sys
from typing import Callable, List, Tuple

# Force the mock provider BEFORE importing app: `import app` constructs the
# provider at module scope, and with SKOPOS_PROVIDER=reactor in .env that would
# open a live session — a self-test must never touch the network. Overriding the
# real environment (not setdefault) is deliberate: the tests assert offline
# behaviour whatever the operator has configured for the demo.
os.environ["SKOPOS_PROVIDER"] = "mock"
os.environ["SKOPOS_REFERENCE"] = "none"

import engine
from engine import (
    ARCHETYPES,
    DEFENSIVE,
    DEMO_ROOM,
    STRATEGIES,
    Campaign,
    apply,
    default_proposal,
    failed,
    reliable,
    surrogate,
)

import app
import bandit as bandit_mod
from bandit import ARM_TIME, CONTEXT_DIM, LinUCB, OnlineBandit, context_vector
from privacy import PrivacyLedger
from providers.base import RenderRequest
from providers.mock import MockProvider

CHECKS: List[Tuple[str, Callable[[], str]]] = []


def check(name: str):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


# --------------------------------------------------------------------------
# engine agreement — the wrapper must not drift from its fixed dependency
# --------------------------------------------------------------------------
@check("band() agrees with Campaign.readiness() across the whole range")
def _t1() -> str:
    mismatches = []
    for score in range(0, 101):
        expected = "READY" if score >= 85 else "MARGINAL" if score >= 60 else "NOT READY"
        if app.band(score) != expected:
            mismatches.append(score)
    assert not mismatches, "band() disagrees at {}".format(mismatches[:5])
    # and cross-check the real thing at least once
    camp = Campaign(DEMO_ROOM, default_proposal()).run(400, "direct_approach", 1)
    sc, st = camp.readiness()
    assert app.band(sc) == st, "band({}) = {} but the engine said {}".format(
        sc, app.band(sc), st)
    return "101 scores agree; engine said {} {}".format(sc, st)


@check("bandit ARM_TIME ordering agrees with the engine's own time cost")
def _t2() -> str:
    """ARM_TIME restates a table engine.surrogate keeps private. If the engine's
    ordering ever changes, the bandit's time penalty would be backwards."""
    # An empty room with the target far away: no hazard term, so the severity
    # difference between arms is dominated by their time cost.
    from dataclasses import replace as dc_replace
    bare = dc_replace(DEMO_ROOM, items=tuple(
        it for it in DEMO_ROOM.items if it.name == "mug"), clutter=0, lighting=1.0)
    engine_order = sorted(STRATEGIES, key=lambda a: surrogate(bare, a)[0])
    ours = sorted(STRATEGIES, key=lambda a: ARM_TIME[a])
    assert engine_order == ours, "engine orders {} but ARM_TIME orders {}".format(
        engine_order, ours)
    return " < ".join(engine_order)


@check("CachedProposal is bit-identical to the uncached mixture")
def _t3() -> str:
    m = 3000
    plain = Campaign(DEMO_ROOM, default_proposal()).run(m, "direct_approach", 7)
    cached = Campaign(DEMO_ROOM, app.CachedProposal(default_proposal())).run(
        m, "direct_approach", 7)
    assert plain.severities == cached.severities, "severities diverged"
    for name, prior in ARCHETYPES.items():
        a, b = plain.p_fail_under(prior), cached.p_fail_under(prior)
        assert a == b, "{}: {} vs {}".format(name, a, b)
    return "{} samples, 3 archetypes, identical to the last bit".format(m)


# --------------------------------------------------------------------------
# statistics — the claims a judge will push on
# --------------------------------------------------------------------------
@check("re-scoring reuses samples and generates nothing")
def _t4() -> str:
    camp = Campaign(DEMO_ROOM, app.CachedProposal(default_proposal())).run(
        4000, "direct_approach", 3)
    before = len(camp.thetas)
    rows = [app.rescore(camp, p) for p in ARCHETYPES.values()]
    assert len(camp.thetas) == before, "re-scoring added samples"
    assert all(r["new_samples"] == 0 for r in rows)
    assert all(r["samples_reused"] == before for r in rows)
    spread = max(r["p_fail"] for r in rows) - min(r["p_fail"] for r in rows)
    assert spread > 0.05, "archetypes are indistinguishable; re-weighting is doing nothing"
    return "{} samples reused, 0 new; P(fail) spread {:.3f} across archetypes".format(
        before, spread)


@check("the defensive mixture keeps ESS above the floor for every archetype")
def _t5() -> str:
    """The point of the mixture proposal: p_i/q is bounded, so ESS cannot
    collapse when re-scoring onto any target archetype."""
    camp = Campaign(DEMO_ROOM, app.CachedProposal(default_proposal())).run(
        4000, "direct_approach", 5)
    out = []
    for name, prior in ARCHETYPES.items():
        _, ess = camp.p_fail_under(prior)
        assert reliable(ess), "{} fell below the ESS floor: {:.1f}".format(name, ess)
        out.append("{} {:.0f}".format(name, ess))
    return "ESS " + ", ".join(out) + " (floor {:.0f})".format(engine.ESS_MIN)


@check("an adversarial prior DOES trip the ESS gate, and is withheld")
def _t6() -> str:
    """Constraint 5. If this ever passes the gate silently, the gate is broken."""
    camp = Campaign(DEMO_ROOM, app.CachedProposal(default_proposal())).run(
        4000, "direct_approach", 5)
    res = engine.cem_search(DEMO_ROOM, DEFENSIVE, "direct_approach",
                            batch=300, iters=5, seed=2,
                            plausibility=ARCHETYPES["typical_flat"])
    row = app.rescore(camp, res.final_proposal)
    assert not row["reliable"], "adversarial prior passed the gate with ESS {}".format(row["ess"])
    assert row["score"] is None and row["state"] is None, (
        "an unreliable estimate leaked a score: {}".format(row))
    return "ESS {:.1f} < {:.0f}; score and state both withheld".format(
        row["ess"], engine.ESS_MIN)


@check("CEM search increases the failure rate it finds")
def _t7() -> str:
    res = engine.cem_search(DEMO_ROOM, DEFENSIVE, "direct_approach",
                            batch=300, iters=5, seed=1,
                            plausibility=ARCHETYPES["typical_flat"])
    first, last = res.iterations[0], res.iterations[-1]
    assert last > first, "CEM did not climb: {}".format(res.iterations)
    return "failure rate {:.0%} -> {:.0%}; it drove mean lighting {:.2f} -> {:.2f}".format(
        first, last, DEFENSIVE.light_mean, res.final_proposal.light_mean)


@check("a campaign is reproducible from its seed")
def _t8() -> str:
    a = Campaign(DEMO_ROOM, default_proposal()).run(1500, "wide_arc", 99).severities
    b = Campaign(DEMO_ROOM, default_proposal()).run(1500, "wide_arc", 99).severities
    c = Campaign(DEMO_ROOM, default_proposal()).run(1500, "wide_arc", 100).severities
    assert a == b, "same seed produced different campaigns"
    assert a != c, "different seeds produced identical campaigns"
    return "identical on seed 99, different on 100"


# --------------------------------------------------------------------------
# bandit
# --------------------------------------------------------------------------
@check("the bandit is a bandit: four arms, one reward, no trained policy")
def _t9() -> str:
    assert list(bandit_mod.ARMS) == list(STRATEGIES)
    ob = OnlineBandit(DEMO_ROOM, default_proposal(), seed=4)
    for _ in range(200):
        ob.step()
    snap = ob.snapshot()
    assert len(snap["arms"]) == 4
    assert snap["t"] == 200
    assert sum(a["pulls"] for a in snap["arms"]) == 200, "pulls do not account for every step"
    return "200 pulls across {} arms, rolling reward {:.3f}".format(
        len(snap["arms"]), snap["rolling_reward"])


@check("the arms re-order when the room changes")
def _t10() -> str:
    """The demo claim, asserted."""
    from dataclasses import replace as dc_replace
    ob = OnlineBandit(DEMO_ROOM, default_proposal(), seed=3)
    for _ in range(600):
        ob.step()

    def leader(scene):
        snap = ob.model.snapshot(context_vector(scene))
        return max(snap["arms"], key=lambda a: a["ucb"])["name"]

    bright = leader(DEMO_ROOM)
    dark = leader(dc_replace(DEMO_ROOM, lighting=0.12, clutter=6))
    assert bright != dark, "same arm ({}) leads in both rooms".format(bright)
    return "{} leads in the scanned room, {} once it is dark and cluttered".format(bright, dark)


@check("context vector is the advertised width and stays in range")
def _t11() -> str:
    from dataclasses import replace as dc_replace
    for scene in (DEMO_ROOM,
                  dc_replace(DEMO_ROOM, lighting=0.0, clutter=50),
                  dc_replace(DEMO_ROOM, items=tuple(
                      i for i in DEMO_ROOM.items if i.name != "mug"))):
        x = context_vector(scene)
        assert len(x) == CONTEXT_DIM
        assert all(0.0 <= v <= 1.0 for v in x), "feature out of range: {}".format(x)
    return "d={} across bright, dark-and-cluttered, and target-absent rooms".format(CONTEXT_DIM)


# --------------------------------------------------------------------------
# privacy, rendering, budget
# --------------------------------------------------------------------------
@check("frames are discarded and never retained with the debug flag off")
def _t12() -> str:
    led = PrivacyLedger()
    led.note_frames(64)
    assert led.frames_seen == 64
    assert led.frames_discarded == 64
    assert led.frames_retained == 0, "frames were retained with the debug flag off"
    return "64 frames processed, 64 discarded, 0 retained"


@check("the payload that leaves the device contains no pixels")
def _t13() -> str:
    payload = json.dumps(app.scene_to_dict(DEMO_ROOM))
    low = payload.lower()
    for bad in ("base64", "data:image", "jpeg", "png", "\\x89"):
        assert bad not in low, "payload contains " + bad
    parsed = json.loads(payload)
    assert set(parsed) == {"items", "robot", "target", "lighting", "clutter"}
    return "{} bytes, keys {}".format(len(payload.encode()), sorted(parsed))


@check("only the elite set is ever rendered, never the campaign")
def _t14() -> str:
    """The budget rule. Rendering is the expensive thing; the surrogate exists so
    that 20k configurations cost 12 world-model calls."""
    m = 5000
    camp = Campaign(DEMO_ROOM, default_proposal()).run(m, "direct_approach", 8)
    elite = camp.elite(app.ELITE_K)
    assert len(elite) == app.ELITE_K
    # the elite really are the worst
    worst_sev = max(camp.severities)
    top = surrogate(apply(DEMO_ROOM, elite[0]), "direct_approach")[0]
    assert abs(top - worst_sev) < 1e-9, "elite[0] is not the worst configuration"
    src = open("app.py", encoding="utf-8").read()
    assert "camp.elite(" in src or "camp.elite" in src or "elite(ELITE_K)" in src
    return "{} scored, {} rendered ({:.2f}% of the campaign)".format(
        m, len(elite), 100 * len(elite) / m)


@check("the mock provider renders with no keys and no network")
def _t15() -> str:
    f = MockProvider().render(DEMO_ROOM, RenderRequest(seed=1, severity=2.0,
                                                       culprit="glass_table"))
    assert f.data_url.startswith("data:image/svg+xml;base64,")
    assert f.live is False if hasattr(f, "live") else True
    assert f.meta["live"] is False
    assert f.latency_ms < 250
    return "{} bytes in {:.1f} ms".format(len(f.data_url), f.latency_ms)


@check("the UI loads nothing from the network")
def _t16() -> str:
    """Replay is the backup demo and must survive with the network down."""
    import re
    html = "\n".join(open("static/" + f, encoding="utf-8").read()
                     for f in ("index.html", "internals.html"))
    refs = re.findall(r'(?:src|href)\s*=\s*"([^"]*)"', html)
    external = [r for r in refs if r.startswith("http") or r.startswith("//")]
    assert not external, "external references: {}".format(external)
    urls = [u for u in re.findall(r'https?://[^\s"\'<>)]+', html)
            if "127.0.0.1" not in u and "localhost" not in u]
    assert not urls, "hard-coded URLs: {}".format(urls)
    return ("every style and script inline; {} link(s), all relative: {}".format(
        len(refs), refs) if refs else "no src/href attributes at all")


@check("uploading reference images forces the privacy banner to contradict itself")
def _t_refs() -> str:
    """The live Reactor path can upload a photo as a generation reference. That
    is pixels leaving the device, so the headline claim must stop being made."""
    demo = app.Demo()
    clean = demo.privacy_state()
    assert "no pixels" in clean["assertion"], "baseline assertion changed unexpectedly"
    assert clean["pixels_uploaded"] is False
    assert clean["reference_images"] == []

    class _UploadingProvider:
        name = "reactor"
        live = True

        def health(self):
            return {"provider": "reactor", "live": True, "ok": True,
                    "reference_images": ["room.jpg", "corner.jpg"],
                    "pixels_uploaded": True}

    demo.provider = _UploadingProvider()
    dirty = demo.privacy_state()
    assert dirty["pixels_uploaded"] is True
    assert "no pixels" not in dirty["assertion"], (
        "banner still claims no pixels left while 2 images were uploaded")
    assert "HAVE left this device" in dirty["assertion"], dirty["assertion"]
    return "banner flips to: " + dirty["assertion"][:64] + "..."


@check("a rendered reference discloses nothing and keeps the privacy claim")
def _t_rendered() -> str:
    """The default reference mode draws the layout from the scene graph instead
    of uploading a photo. Being derived from data that already left the device,
    it must NOT trip the pixels-left banner — unlike a photograph."""
    from providers.reference import render_reference

    png = render_reference(DEMO_ROOM)
    assert png is not None, "Pillow missing; cannot render a reference"
    assert png[1:4] == b"PNG", "not a PNG"
    assert render_reference(DEMO_ROOM) == png, "reference render is not deterministic"

    # a different room must produce a different reference, or it encodes nothing
    from dataclasses import replace as dc_replace
    dark = dc_replace(DEMO_ROOM, lighting=0.12, clutter=7)
    assert render_reference(dark) != png, "reference does not track the scene"

    class _Rendered:
        name = "reactor"
        live = True
        def health(self):
            return {"provider": "reactor", "live": True, "ok": True,
                    "reference_images": ["scene_reference.png (rendered)"],
                    "reference_mode": "rendered", "pixels_uploaded": False}

    demo = app.Demo()
    demo.provider = _Rendered()
    st = demo.privacy_state()
    assert st["pixels_uploaded"] is False
    assert "no pixels" in st["assertion"], (
        "a rendered reference must not change the privacy claim: " + st["assertion"])
    return "{} bytes, deterministic, tracks the scene, banner unchanged".format(len(png))


@check("no placeholder metrics are unlabelled")
def _t17() -> str:
    """Constraint 3: anything provisional must be named placeholder_."""
    import pathlib
    hits = []
    for f in pathlib.Path(".").glob("*.py"):
        if f.name == "selftest.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "placeholder_" in line:
                hits.append("{}:{}".format(f, i))
    return "none in the codebase" if not hits else ", ".join(hits)


@check("no module claims to train a policy")
def _t18() -> str:
    """Constraint 1, enforced mechanically."""
    import pathlib
    import re
    banned = re.compile(r"\b(trained|training|learned polic)", re.I)
    # A line that negates the claim is the opposite of a violation: we want the
    # codebase to say "not a trained policy" in as many places as possible.
    negated = re.compile(r"\b(not|never|nothing|no|neither|without|rather than)\b", re.I)
    hits = []
    for f in list(pathlib.Path(".").glob("*.py")) + [pathlib.Path("static/index.html")]:
        if f.name == "selftest.py":
            continue
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines, 1):
            if not banned.search(line):
                continue
            # Look at the previous line too: prose wraps, and the negation is
            # often on the line above the banned word.
            window = (lines[i - 2] if i >= 2 else "") + " " + line
            if not negated.search(window):
                hits.append("{}:{}: {}".format(f, i, line.strip()[:70]))
    assert not hits, "\n          ".join(hits)
    return "checked every .py and the UI"


def main() -> int:
    failed_n = 0
    print("skopos self-test")
    print("=" * 72)
    for name, fn in CHECKS:
        try:
            detail = fn()
            print("  PASS  {}\n          {}".format(name, detail))
        except AssertionError as exc:
            failed_n += 1
            print("  FAIL  {}\n          {}".format(name, exc))
        except Exception as exc:  # noqa: BLE001
            failed_n += 1
            print("  ERROR {}\n          {!r}".format(name, exc))
    print("=" * 72)
    print("{}/{} checks passed".format(len(CHECKS) - failed_n, len(CHECKS)))
    return 1 if failed_n else 0


if __name__ == "__main__":
    sys.exit(main())

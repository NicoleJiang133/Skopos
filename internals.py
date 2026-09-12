"""
Internals: everything the demo does under the surface, shaped for drawing.

This module reads a finished `Campaign`, the bandit and the CEM result and turns
them into arrays a canvas can plot. It computes nothing the engine already
computes — no failure model is re-implemented here, because a second copy of the
engine's logic would drift from it. Where a quantity is not exposed by
engine.py, it is *derived from engine outputs* (severities, thetas, weights)
rather than recalculated from the engine's internals.

Everything here is read-only with respect to the campaign.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import engine
from engine import ARCHETYPES, Campaign, Prior, SceneGraph

# Plot budgets. A campaign is 20k samples; nobody needs 20k points on screen and
# the JSON would be megabytes.
SCATTER_POINTS = 1200
HIST_BINS = 44
AXIS_BINS = 14


def _hist(values: Sequence[float], bins: int, lo: Optional[float] = None,
          hi: Optional[float] = None) -> Dict[str, Any]:
    if not values:
        return {"edges": [], "counts": [], "lo": 0.0, "hi": 0.0, "max": 0}
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    if hi <= lo:
        hi = lo + 1e-9
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        i = int((v - lo) / width)
        counts[min(max(i, 0), bins - 1)] += 1
    edges = [lo + i * width for i in range(bins + 1)]
    return {"edges": [round(e, 4) for e in edges], "counts": counts,
            "lo": round(lo, 4), "hi": round(hi, 4), "max": max(counts)}


def _stride(n: int, want: int) -> int:
    return max(1, n // max(want, 1))


def _theta_summary(theta) -> Dict[str, float]:
    """Reduce one perturbation vector to the few numbers worth plotting."""
    disp = [math.hypot(dx, dy) for dx, dy in theta.offsets]
    return {
        "max_disp": max(disp) if disp else 0.0,
        "mean_disp": (sum(disp) / len(disp)) if disp else 0.0,
        "removed": sum(1 for r in theta.removed if r),
        "lighting": theta.lighting,
        "clutter": theta.clutter,
    }


def _binned_mean(xs: Sequence[float], ys: Sequence[float], bins: int,
                 lo: Optional[float] = None, hi: Optional[float] = None) -> Dict[str, Any]:
    """Mean failure rate (or severity) as a function of one perturbation axis.

    This is the honest way to show 'which axis drives failure': it is measured
    off the campaign's own samples, not asserted from the engine's formula.
    """
    if not xs:
        return {"centres": [], "means": [], "counts": []}
    lo = min(xs) if lo is None else lo
    hi = max(xs) if hi is None else hi
    if hi <= lo:
        hi = lo + 1e-9
    width = (hi - lo) / bins
    sums = [0.0] * bins
    counts = [0] * bins
    for x, y in zip(xs, ys):
        i = min(max(int((x - lo) / width), 0), bins - 1)
        sums[i] += y
        counts[i] += 1
    centres = [lo + (i + 0.5) * width for i in range(bins)]
    means = [(sums[i] / counts[i]) if counts[i] else None for i in range(bins)]
    return {
        "centres": [round(c, 4) for c in centres],
        "means": [None if m is None else round(m, 4) for m in means],
        "counts": counts,
        "lo": round(lo, 4), "hi": round(hi, 4),
    }


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------
def monte_carlo(camp: Campaign, scene: SceneGraph) -> Dict[str, Any]:
    sev = camp.severities
    n = len(sev)
    fails = [engine.failed(s) for s in sev]
    summaries = [_theta_summary(t) for t in camp.thetas]

    # severity distribution, with the engine's own failure threshold marked
    hist = _hist(sev, HIST_BINS, lo=0.0, hi=max(sev) if sev else 1.0)

    # where does the target end up across samples? this is the perturbation
    # space made visible — sampled, never enumerated
    try:
        t_idx = [i for i, it in enumerate(scene.items) if it.name == scene.target][0]
    except IndexError:
        t_idx = 0
    base = scene.items[t_idx]
    step = _stride(n, SCATTER_POINTS)
    scatter = []
    for i in range(0, n, step):
        dx, dy = camp.thetas[i].offsets[t_idx]
        scatter.append({
            "x": round(base.x + dx, 3),
            "y": round(base.y + dy, 3),
            "f": 1 if fails[i] else 0,
            "s": round(sev[i], 2),
            "gone": 1 if camp.thetas[i].removed[t_idx] else 0,
        })

    # failure rate as a function of each perturbation axis
    axes = {
        "lighting": _binned_mean([s["lighting"] for s in summaries],
                                 [1.0 if f else 0.0 for f in fails], AXIS_BINS, 0.0, 1.0),
        "clutter": _binned_mean([float(s["clutter"]) for s in summaries],
                                [1.0 if f else 0.0 for f in fails], 10, 0.0, 10.0),
        "max_disp": _binned_mean([s["max_disp"] for s in summaries],
                                 [1.0 if f else 0.0 for f in fails], AXIS_BINS),
        "removed": _binned_mean([float(s["removed"]) for s in summaries],
                                [1.0 if f else 0.0 for f in fails], 6, 0.0, 6.0),
    }

    # running estimate: how the Monte Carlo estimate converges
    running = []
    hits = 0
    every = max(1, n // 120)
    for i, f in enumerate(fails, 1):
        hits += 1 if f else 0
        if i % every == 0 or i == n:
            p = hits / i
            # 95% binomial interval, the honest error bar on a MC estimate
            se = math.sqrt(max(p * (1 - p), 1e-12) / i)
            running.append({"n": i, "p": round(p, 4),
                            "lo": round(max(0.0, p - 1.96 * se), 4),
                            "hi": round(min(1.0, p + 1.96 * se), 4)})

    return {
        "n": n,
        "threshold": engine.FAIL_THRESHOLD,
        "p_fail": round(camp.p_fail(), 4),
        "severity_hist": hist,
        "scatter": scatter,
        "scatter_of": scene.target,
        "scatter_stride": step,
        "axes": axes,
        "running": running,
        "severity_max": round(max(sev), 3) if sev else 0.0,
    }


# ---------------------------------------------------------------------------
# importance weighting
# ---------------------------------------------------------------------------
def weights(camp: Campaign) -> Dict[str, Any]:
    """Per-archetype weight distribution, ESS, and how concentrated it is.

    The weight ratio is recomputed the same way Campaign.p_fail_under does, from
    the same two log_pdf calls, so what is drawn is what the estimator used.
    """
    out = []
    for name, prior in ARCHETYPES.items():
        logw = [prior.log_pdf(t) - camp.proposal.log_pdf(t) for t in camp.thetas]
        mx = max(logw)
        w = [math.exp(lw - mx) for lw in logw]
        sw = sum(w)
        ess = (sw ** 2) / sum(x * x for x in w) if sw > 0 else 0.0
        # normalised weights, biggest first: how much of the estimate rests on
        # how few samples
        norm = sorted((x / sw for x in w), reverse=True) if sw > 0 else []
        cum, top = 0.0, []
        for i, v in enumerate(norm[:200]):
            cum += v
            if i in (0, 4, 9, 49, 99, 199):
                top.append({"k": i + 1, "share": round(cum, 4)})
        # The log-weight distribution has a long left tail — a handful of
        # samples the archetype finds essentially impossible. Plotting the full
        # range squashes all the mass into one bar, so histogram the bulk and
        # report the tail as a number instead of drawing it.
        srt = sorted(logw)
        p01 = srt[int(0.01 * (len(srt) - 1))]
        below = sum(1 for v in logw if v < p01)
        hist = _hist([v for v in logw if v >= p01], HIST_BINS, lo=p01, hi=max(logw))
        hist["clipped_below"] = below
        hist["clip_at"] = round(p01, 3)
        hist["true_min"] = round(min(logw), 3)

        est, _ = camp.p_fail_under(prior)
        out.append({
            "name": name,
            "p_fail": round(est, 4),
            "ess": round(ess, 1),
            "ess_frac": round(ess / len(w), 4) if w else 0.0,
            "reliable": bool(engine.reliable(ess)),
            "logw_hist": hist,
            "concentration": top,
            "prior": {
                "move_sigma": prior.move_sigma, "remove_p": prior.remove_p,
                "light_mean": prior.light_mean, "light_sigma": prior.light_sigma,
                "clutter_lambda": prior.clutter_lambda,
            },
        })
    return {"rows": out, "ess_min": engine.ESS_MIN,
            "proposal": camp.proposal.name, "n": len(camp.thetas)}


# ---------------------------------------------------------------------------
# the bandit's own internals
# ---------------------------------------------------------------------------
def bandit_internals(ob) -> Dict[str, Any]:
    """theta, the uncertainty term and the design matrix — the actual model.

    The bars in the main UI show the output; this shows the linear model that
    produced it.
    """
    from bandit import CONTEXT_FEATURES, _dot, _inv, _matvec, context_vector

    x = context_vector(ob.scene)
    model = ob.model
    arms = []
    for name in model.arms:
        st = model.state[name]
        Ainv = _inv(st.A)
        theta = _matvec(Ainv, st.b)
        var = max(_dot(x, _matvec(Ainv, x)), 0.0)
        bonus = model.alpha * math.sqrt(var)
        mean = _dot(theta, x)
        arms.append({
            "name": name,
            "theta": [round(v, 4) for v in theta],
            # per-feature contribution to the predicted value: theta_i * x_i.
            # This is what makes the model readable rather than a black box.
            "contribution": [round(theta[i] * x[i], 4) for i in range(len(x))],
            "mean": round(mean, 4),
            "bonus": round(bonus, 4),
            "ucb": round(mean + bonus, 4),
            "pulls": st.pulls,
            "fail_rate": round(st.fail_count / st.pulls, 4) if st.pulls else 0.0,
            "empirical": round(st.reward_sum / st.pulls, 4) if st.pulls else 0.0,
            # diagonal of the design matrix: how much evidence per feature
            "a_diag": [round(st.A[i][i], 3) for i in range(len(x))],
        })
    return {
        "features": list(CONTEXT_FEATURES),
        "context": [round(v, 4) for v in x],
        "alpha": model.alpha,
        "warmup": model.warmup,
        "t": model.t,
        "arms": arms,
        "reward_history": [round(v, 3) for v in ob.history[-240:]],
        "rolling_reward": round(ob.rolling_reward(), 4),
    }


# ---------------------------------------------------------------------------
def cem_internals(cem: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """CEM is already summarised by app.run_cem; pass it through unchanged."""
    return cem


def snapshot(demo) -> Dict[str, Any]:
    """Everything, for one page load."""
    camp = demo.campaign
    import app as _app
    out: Dict[str, Any] = {
        "has_campaign": camp is not None,
        "scene": _app.scene_to_dict(demo.scene),
        "pipeline": {
            "scored": len(camp.thetas) if camp else 0,
            "rendered": demo_elite_k(),
            "payload_bytes": demo.ledger.bytes_out,
            "payloads": demo.ledger.payloads_out,
            "frames_seen": demo.ledger.frames_seen,
            "frames_retained": demo.ledger.frames_retained,
            "strategy": demo.strategy,
            "seed": demo.seed,
        },
    }
    if camp is not None:
        out["monte_carlo"] = monte_carlo(camp, demo.scene)
        out["weights"] = weights(camp)
        out["readiness"] = dict(zip(("score", "state"), camp.readiness()))
    if demo.bandit is not None:
        out["bandit"] = bandit_internals(demo.bandit)
    out["cem"] = cem_internals(demo.cem)
    return out


def demo_elite_k() -> int:
    import app
    return app.ELITE_K

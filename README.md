# Skopos

**A pre-deployment readiness check for home robots.** Scan a room, sample
thousands of plausible variants of it, find where a fetch task fails, and get a
verdict — before the robot ships to that home.

> A home robot should meet your home before it ships to your home.

---

## Quickstart

```bash
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8077
open http://127.0.0.1:8077
```

No API keys, no network, no npm. `python selftest.py` checks every claim below.

## Architecture in five bullets

- **`engine.py`** is the sampling engine and a **fixed dependency** — scene
  graph, surrogate scorer, Monte Carlo campaigns, importance re-weighting and
  cross-entropy search. Stdlib only. Nothing else in this repo modifies it.
- **A campaign scores on the scene graph, never on pixels.** ~20,000
  configurations per run through a microsecond surrogate; **twelve** of them get
  a world-model call. That ratio is the point.
- **Sample once, re-score many times.** A defensive mixture proposal bounds the
  importance weights, so the same samples can be re-weighted onto any home
  archetype for **zero new generations** — with the effective sample size shown
  next to every estimate.
- **`bandit.py`** is a contextual bandit (LinUCB) over four task strategies,
  adapting online as the room changes.
- **`app.py`** is FastAPI + one WebSocket; **`static/index.html`** is the entire
  front end — vanilla JS, no build step, no external requests. A second page,
  **`/internals`**, shows the machinery itself.

```
scan ──▶ SceneGraph ──┬──▶ surrogate ──▶ campaign ──▶ readiness + hazards
    [pixels stop here] │                     ├──▶ re-weight ──▶ per-archetype verdict
                       │                     └──▶ elite(12) ──▶ world-model render
                       ├──▶ cross-entropy search ──▶ rare-but-plausible failures
                       └──▶ contextual bandit ──▶ strategy selection
```

---

## What this is not — please read before judging

1. **Online adaptation is a contextual bandit, not a trained policy.** A bandit
   is the one-step case of reinforcement learning: one decision, one reward, no
   state transition, no credit assignment over time. Nothing in this repo is
   trained. `selftest.py` greps the whole codebase to enforce it.
2. **This is not a digital twin.** There is no metric ground truth, no collision
   mesh, no physics and no SLAM. Positions are approximate metres in a
   room-local frame, and the failure model is a hand-written geometric and
   semantic surrogate whose every coefficient is visible in `engine.py`. A
   perturbed room is a *plausible* hypothesis about how a home might differ, not
   a measurement of one.
3. **The rendered frames are a mock by default.** `providers/mock.py` draws a
   stylised plan view and is what you see unless you supply credentials. It is
   labelled `MOCK RENDER / not a world model` inside the image itself.
4. **The Reactor path has now been run live, and here is exactly what was
   measured** (`reactor/helios`, 12 Sept 2026): connect in ~9 s, **16 fps** at
   1280×768, all 12 elite renders returning live frames under 0.25 s old.
   The model's own `request_schema()` output is committed at
   `docs/reactor-helios-schema.json`. Two things it does *not* do: it is
   prompt-conditioned, so the render is a plausible room consistent with the
   scene graph's description rather than a faithful reconstruction of it; and it
   is subject to capacity — a `429 no available capacity` is a normal response,
   which is why the provider retries with backoff and falls back to mock frames
   that are labelled as mock.
5. **The demo room is hand-written**, not scanned. `DEMO_ROOM` in `engine.py` is
   six objects a human typed in. No vision model ran.
6. **The readiness thresholds are a judgement call**, not a result:
   READY ≥ 85, MARGINAL ≥ 60. `readiness = 100 × (1 − P(failure))`.
7. **The archetype priors are assumptions**, not measurements of real homes.

Anything provisional is named with a `placeholder_` prefix. There are currently
none, and the self-test fails if one appears unlabelled.

## The statistics, and the one rule that matters

We want `P(failure)` under several home archetypes. Sampling each archetype
separately would cost a full campaign each. Instead we sample **once** from a
defensive mixture proposal and re-weight:

```
P_i(fail) ≈ Σ w_m · 1(fail_m) / Σ w_m ,    w_m = p_i(θ_m) / q(θ_m)
```

`q` mixes every target archetype plus one deliberately over-dispersed component,
which bounds `p_i/q ≤ K` and floors the effective sample size at roughly `M/K`.
That is what makes re-scoring statistically honest rather than a trick.

**And the rule: an importance-weighted estimate is never displayed when its
effective sample size is too small.** Below `ESS_MIN = 200` the weights have
degenerated onto a handful of samples and the number is noise, so the UI greys
the row out and shows the ESS instead — and the headline verdict becomes a
hatched **ESS TOO LOW** panel rather than a score.

You can watch this fire. Run the adversarial search, then select
**adversarial (CEM)** in the archetype dropdown: the converged prior sits far
from the proposal, ESS collapses to around 50, and the verdict is withheld.
Measured, in `selftest.py`, not asserted.

## The engine room — `/internals`

The demo page shows conclusions. **[`/internals`](http://127.0.0.1:8077/internals)**
shows the machinery that produced them, on one page, every chart drawn on a raw
`<canvas>` with no plotting library:

| panel | what it shows |
| --- | --- |
| **pipeline** | 1 scene graph → 20,000 configurations → 20,000 surrogate calls → 12 world-model calls. The ratio that justifies the whole design, with live counters |
| **monte carlo** | the severity of every sampled room as a histogram, with the engine's own `FAIL_THRESHOLD` drawn on it and the failing mass in red |
| **convergence** | P(failure) as samples accumulate, with its 95% binomial interval narrowing as 1/√n — precision being bought, and the price visible |
| **perturbation space** | where the mug actually landed across ~1,200 sampled rooms, red for failed. A continuous space with nothing to enumerate |
| **what drives failure** | failure rate against each perturbation axis, measured off the campaign's own samples. The lighting panel is the finding: ~100% failure in the darkest rooms against ~23% in the brightest |
| **importance weighting** | the log-weight distribution per archetype (log-scaled counts, so the tail is visible), ESS bars against the floor, and how much of each estimate rests on its top 50 samples |
| **contextual bandit** | the UCB decomposition (solid = θ·x, faint = the exploration bonus) and a per-feature heatmap of θᵢ·xᵢ. The entire model is five numbers per arm, and they are on screen |
| **adversarial search** | the CEM failure rate climbing per iteration, and the proposal's own parameters before and after — `light_mean` 0.68 → 0.06, discovered, not told |

Nothing on that page re-implements the engine. Every number is derived from
engine outputs — severities, thetas, weights — because a second copy of the
failure model would drift from the first.

## What you can do in the UI

| control | what happens |
| --- | --- |
| **Run campaign** | streams 20,000 samples in ten chunks; the readiness estimate visibly settles rather than jumping, then the worst twelve rooms are rendered |
| **archetype dropdown** | re-weights the *existing* campaign onto another home — 0 new generations, ESS shown for each |
| **Clear the worst hazard** | acts on the report: moves the worst attributed object off the robot's path and re-measures |
| **move an object** | drag x/y; dragging updates the graph and the render, releasing re-measures |
| **Run search** | cross-entropy search refits the sampler to its own worst outcomes |
| **Record / Replay** | dumps a run to `runs/<id>/` and plays it back from disk with nothing on the network |

There is deliberately **no lighting slider**. `engine.apply()` overwrites
`scene.lighting` with the sampled `theta.lighting`, so editing the base scene's
lighting would change the render and change nothing about the measurement.
Lighting and clutter are sampled perturbation axes, not properties of the scan —
you change them by switching archetype.

## Measured on the build machine

| | |
| --- | --- |
| surrogate throughput | ~6,400 samples/s (not the 35,000 quoted for `engine.py` elsewhere — measure yours) |
| 20,000-sample campaign | ~1.2–3.1 s, on a worker thread so the socket never stalls |
| re-weighting onto another archetype | ~460 ms, **0 new generations** |
| cross-entropy search | 5 × 400 samples in ~150 ms; failure rate 46% → 100% |
| rendered frames per campaign | **12 of 20,000** (0.06%) |

A representative run: the scanned room scores **64 MARGINAL** with the glass
table causing half the failures. Clear it → **72**, and the dark rug becomes the
bottleneck. Clear that → **81**, and what remains is the mug simply not being
there, which no amount of moving furniture fixes.

## Privacy

### Why the reference image is off by default — a measurement, not a preference

A world model conditioned on text alone throws away the geometry the surrogate
scores on, so it wants a reference image. The obvious way to get one — photograph
the room — sends pixels to a third party and destroys the claim below.

So Skopos **draws the reference instead** (`providers/reference.py`): an overhead
plan of the room, objects sized by their real radius and tinted by what the
engine cares about (reflective cold and bright, low-contrast near-black), with
the robot-to-target line drawn in.

The important property is not that it is "synthetic". It is that the image is a
**pure function of the scene graph**, and the scene graph is already the one
artefact that leaves the device — so it discloses *nothing new*. No camera
contributed to it, and you could redraw it by hand from the JSON in the privacy
panel. Uploading it is not a weaker version of uploading a photo; it is a
different thing.

| `SKOPOS_REFERENCE` | what is uploaded | privacy claim |
| --- | --- | --- |
| `none` *(default)* | nothing | holds |
| `rendered` | a plan drawn from the scene graph | **holds** — zero additional information crosses the boundary |
| `photo` | the files in `SKOPOS_REFERENCE_IMAGES` | **broken**, and the app says so in the log, the provider health, the privacy panel and the banner |

**But conditioning on the rendered plan was measured and it does not work.**
Against `reactor/helios`:

| setup | result |
| --- | --- |
| prompt only | a photorealistic living room. This is the default |
| rendered plan, `image_strength` 1.0 | the model animates **the diagram**. The schema says 1.0 "locks the first frame to the reference", and it does |
| rendered plan, `image_strength` 0.25 | a photo-textured version of the same diagram: the circles survive, the room does not |

The model inherits the reference's geometry at any strength, and a top-down
schematic is not the geometry of an eye-level shot. So the machinery is built,
tested and documented, and switched **off**, because switching it on makes the
output worse. What would work is an *eye-level* render of the scene graph rather
than a plan; that is real work and is not built.

The privacy argument above still stands and the self-test still asserts both
directions — a rendered reference leaves the banner alone, a photograph flips
it. It is simply not the best-looking option today.

### The rest

Frames are processed in memory and discarded. Only the scene graph — structured
text — crosses a network boundary, and the UI shows the exact payload live next
to a counter for frames processed, frames discarded, frames written to disk and
a permanent `pixels transmitted: 0`.

Nothing is written to disk outside `SKOPOS_DEBUG_KEEP_FRAMES=1`, which defaults
off; when it is on, the startup assertion shouts about it and the panel turns
red. The assertion is logged at startup:

> `PRIVACY: frames are processed in memory and discarded; only the SceneGraph
> (structured text, no pixels) leaves this device.`

## Configuration

Copy `.env.example` to `.env` (gitignored; there are no secrets in the code).

| variable | default | meaning |
| --- | --- | --- |
| `SKOPOS_PROVIDER` | `mock` | `mock` \| `reactor` \| `runware` |
| `SKOPOS_SAMPLES` | `20000` | campaign size |
| `SKOPOS_SEED` | `20260912` | seed; a campaign is reproducible from it |
| `REACTOR_API_KEY` | — | see `docs/PROVIDER_SWAP.md` |
| `RUNWARE_API_KEY` | — | fallback provider |
| `SKOPOS_DEBUG_KEEP_FRAMES` | `0` | **debug only**; `1` writes raw frames to disk |

Going live: **`docs/PROVIDER_SWAP.md`** is a ten-minute checklist.

## Licence

MIT.

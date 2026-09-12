# Skopos

**A pre-deployment readiness check for home robots.** Scan your room, and Skopos
generates perturbed variants of it, runs a household task across them, and tells
you where the robot fails — before the robot is in your house.

> A home robot should meet your home before it ships to your home.

---

## Quickstart

```bash
pip install -r requirements.txt
./run.sh                     # or: make dev   (Windows: see below)
open http://127.0.0.1:8077
```

No API keys. No network. No npm. The default providers are mocks and the whole
app runs end to end offline.

On Windows PowerShell, `run.sh` needs a POSIX shell; use this instead:

```powershell
python -m uvicorn skopos.server:app --host 127.0.0.1 --port 8077
```

Then `python -m skopos.selftest` to check that every claim below still holds.

## Architecture in five bullets

- **`perception/`** turns frames into a `SceneGraph`. **Pixels stop here.**
- **`scene_graph.py`** is the central typed object — objects, approximate poses,
  materials, hazard flags. Every other module depends only on it.
- **`sampler/`** draws perturbed rooms from a prior over six named axes by Monte
  Carlo, with importance weighting so rare-but-severe rooms get scored without
  being enumerated.
- **`agent/`** attempts one task ("fetch the mug from the table") using one of
  four discrete strategies chosen by a **contextual bandit**.
- **`providers/`** render a `SceneGraph` through a world model. `mock.py` is
  synthetic and needs nothing; `reactor.py` targets Reactor's real-time API.

```
scan (frames)
  └─> perception/     VLM or mock  ->  SceneGraph      [pixels stop here]
        └─> SceneGraph
              ├─> sampler/    perturbation sampling under a prior + IS weights
              │     └─> perturbed SceneGraph
              │           └─> providers/  world-model render
              ├─> agent/      task attempt + contextual bandit
              └─> metrics/    success rate, hazard attribution, readiness
```

---

## What this is not — please read before judging

These are the limits of the build, stated plainly.

1. **We are not training a policy.** Online adaptation is a **contextual bandit**
   (LinUCB) over four discrete strategies. A bandit is the one-step case of
   reinforcement learning — no state transitions, no credit assignment over
   time. Nothing in this repo is trained, and the words "trained" and "learned
   policy" appear nowhere in the code. See `skopos/agent/bandit.py`.

2. **We are not building a digital twin.** Generated rooms are *plausible*, not
   accurate. There is no metric ground truth, no collision mesh, no SLAM, no
   physics. Poses are approximate numbers in a room-local frame. A perturbed
   room is a hypothesis about how your room might differ tomorrow, not a
   measurement of it.

3. **The task outcome is a simulator, not a robot.** `agent/task.py` samples
   success, hazard contact and duration from a hand-specified generative model
   whose every coefficient is visible in that file. We chose an explicit,
   readable failure model over pretending a controller is executing. Swapping in
   a real rollout changes nothing else in the system.

4. **The demo room is hand-authored.** `perception/mock.py` contains a room a
   human wrote down; no vision model ran. The Claude-backed perception path in
   `perception/claude_vlm.py` is real code but was not exercised against real
   frames during the build.

5. **The Reactor adapter has never run against the live API.** It is written
   against the public docs (read at build time) and every unverified assumption
   is marked `TODO(reactor)` in `providers/reactor.py`. The headline number you
   see on screen comes from the mock renderer, and the UI says `mock` in the
   provider badge when it does.

6. **The readiness thresholds are a judgement call**, not a result.
   READY ≥ 75, MARGINAL ≥ 50. Argue with them; the formula is printed on screen.

7. **The perturbation rates are assumptions**, not measurements. They are priors
   over how often a living room changes, set by hand. The UI labels them
   "rates, not measurements".

Any placeholder metric in this codebase is named with a `placeholder_` prefix so
it is impossible to mistake for a real one. The self-test checks for them; there
are currently none.

---

## Privacy — a headline feature, not a footnote

- Frames are processed into a `SceneGraph` **in memory and then discarded**.
  Nothing is written to disk outside `SKOPOS_DEBUG_KEEP_FRAMES=1`, which
  defaults off and prints a shouting warning at startup when it is on.
- **Only the `SceneGraph` — structured text — crosses a network boundary.**
- The UI has a **"what leaves your device"** panel showing the exact JSON
  payload live, next to a frames-seen / frames-discarded / frames-retained
  counter and a permanent `pixels sent: 0`. You can read the payload on screen
  and confirm there is not a pixel in it.
- The startup log prints:

  > `PRIVACY: frames are processed in memory and discarded; only the SceneGraph
  > (structured text, no pixels) leaves this device.`

**The one caveat, stated honestly:** if you run with `SKOPOS_PERCEPTION=claude`,
the network boundary moves *inside* perception — your scan frames go to the
Claude API exactly once, and the SceneGraph comes back. The default
(`SKOPOS_PERCEPTION=mock`) never leaves the machine at all.

---

## Combinatorics: sample, never enumerate

The joint space of object presence × pose × material × lighting over ten objects
is astronomically large, so we never materialise it.

**Six axes**, each with a *rate* (how often it fires) and a *magnitude*
distribution (how big it is when it does): `object_moved`, `object_removed`,
`lighting`, `occlusion`, `clutter_added`, `reflective_surface`.

**Monte Carlo with importance weighting.** We draw rooms from a tilted proposal
`q` that fires the axes more often and harder than the prior `p`, then correct:

```
w(room) = p(room) / q(room)
E_p[f] ≈ Σ wᵢ fᵢ / Σ wᵢ          (self-normalised)
```

Because the axes are independent, both densities factorise and the weight is a
product of per-axis ratios. With `r' = r^(1-tilt) ≥ r`, an *active* axis is
discounted (`w < 1`, we over-drew it) and an *inactive* axis is credited
(`w > 1`, we under-drew it). At `tilt = 0` the proposal *is* the prior and every
weight is exactly `1.0` — the self-test asserts this to eleven decimal places.

Weights are **truncated to [0.1, 10]** (Ionides-style truncated importance
sampling): raw ESS collapsed below 1% of the sample count at high tilt, and this
trades a small known bias for a large variance reduction. The raw weight is kept
alongside the clipped one. Kish's **effective sample size** is on screen, and the
readiness score's coverage term is driven by it, so a run whose weights have
collapsed cannot quietly score well.

Everything is driven by a seeded RNG. **The seed is in the UI header**, and
`python -m skopos.selftest` verifies that the same seed reproduces a run
attempt-for-attempt.

The self-test also checks the weighting numerically: it estimates the prior mean
of an axis from *tilted* samples and compares it against samples drawn straight
from the prior. They agree to ~2e-4.

---

## The agent and the bandit

One task: **fetch the mug from the table.** Four strategies:

| arm | behaviour |
| --- | --- |
| `direct_approach` | shortest path, no re-look |
| `wide_arc` | detour around flagged objects |
| `slow_scan_then_approach` | re-perceive, then move slowly |
| `request_human_assist` | stop and ask a human |

**LinUCB, not epsilon-greedy**, for three reasons, all in the module docstring:
the value of an arm genuinely depends on the room so a linear model shares
strength across contexts and re-orders within tens of episodes; LinUCB carries an
explicit uncertainty term `α·√(xᵀA⁻¹x)` that we *draw on screen* as the lighter
segment of each bar, whereas epsilon-greedy's exploration is an invisible coin
flip; and it is closed-form, so a replay reproduces the bars exactly.

Reward, all terms in [0, 1]:

```
r = success − 0.45·hazard_contact − 0.25·(time/60s) − 0.30·asked_for_help
```

Asking a human nearly always completes the task but is heavily discounted, so it
only wins where the other arms are genuinely unreliable.

**Watch the four bars re-order when the room shifts. That is the demo.**

## Readiness score

```
R = 100 · ( 0.45·S_w + 0.25·(1 − H_w) + 0.20·coverage + 0.10·timeliness )
```

`S_w` and `H_w` are the importance-weighted success and hazard-contact rates;
`coverage` is ESS against a 15-room budget; `timeliness` is `1 − mean_time/60s`.
The coverage term is a *confidence discount* — a run that has seen three rooms
cannot score highly no matter how well it did. Bands: **READY ≥ 75**,
**MARGINAL ≥ 50**, **NOT READY** below.

The score, the formula and the big state word are all on screen together.

---

## Record and replay

- **Record run** dumps frames, metrics, config, prior and seed to
  `runs/<run-id>/` (`meta.json`, `events.jsonl`, `metrics.json`, `bandit.json`).
- **Replay** plays a recorded run back from disk with **no provider calls and no
  outbound network** — the page loads zero external resources, so a replay works
  with the network cable out. It is the backup demo.

The frames inside a recording are *renders of the SceneGraph*. The user's camera
frames were discarded at perception and never reach the recorder.

## Configuration

Copy `.env.example` to `.env` (gitignored; there are no secrets in the code).

| variable | default | meaning |
| --- | --- | --- |
| `SKOPOS_PROVIDER` | `mock` | `mock` \| `reactor` \| `runware` |
| `SKOPOS_PERCEPTION` | `mock` | `mock` \| `claude` |
| `REACTOR_API_KEY` | — | see `docs/PROVIDER_SWAP.md` |
| `RUNWARE_API_KEY` | — | fallback provider |
| `ANTHROPIC_API_KEY` | — | for `SKOPOS_PERCEPTION=claude` |
| `SKOPOS_DEBUG_KEEP_FRAMES` | `0` | **debug only**; `1` writes raw frames to disk |

Going from mock to live: **`docs/PROVIDER_SWAP.md`** is a ten-minute checklist.

## Licence

MIT.

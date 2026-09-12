"""
Skopos server: FastAPI + one WebSocket carrying the live loop.

`engine.py` is a fixed dependency and is never modified here. This module owns
run state, scheduling and transport; every number it reports comes out of the
engine.

Campaigns are CPU-bound (measured ~6.4k samples/s on the build machine, so a
20k-sample campaign takes about three seconds). They therefore run on a worker
thread via asyncio.to_thread, never on the event loop, or the WebSocket would
stall mid-demo.
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import engine
from engine import (
    ARCHETYPES,
    DEMO_ROOM,
    STRATEGIES,
    Campaign,
    Item,
    SceneGraph,
    default_proposal,
    reliable,
)
from bandit import OnlineBandit
from privacy import PrivacyLedger, startup_assertion
from providers.base import RenderRequest, WorldModelProvider
from recorder import Recorder, list_runs, replay_events

log = logging.getLogger("skopos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

DEFAULT_M = int(os.getenv("SKOPOS_SAMPLES", "20000"))
DEFAULT_SEED = int(os.getenv("SKOPOS_SEED", "20260912"))
ELITE_K = 12
# Bandit pacing. A tick is microseconds, so the interval is purely about
# making the bars legible to a human watching them move.
BANDIT_TICKS_PER_FRAME = 3
BANDIT_INTERVAL_MS = 110


def build_provider(name: Optional[str] = None) -> WorldModelProvider:
    name = (name or os.getenv("SKOPOS_PROVIDER", "mock")).lower()
    if name == "reactor":
        from providers.reactor import ReactorProvider
        return ReactorProvider()
    if name == "runware":
        from providers.runware import RunwareProvider
        return RunwareProvider()
    from providers.mock import MockProvider
    return MockProvider()


# ---------------------------------------------------------------------------
# serialisation helpers — the scene graph is the only thing that leaves here
# ---------------------------------------------------------------------------
def scene_to_dict(sg: SceneGraph) -> Dict[str, Any]:
    return {
        "items": [
            {
                "name": it.name, "x": round(it.x, 3), "y": round(it.y, 3),
                "radius": it.radius, "reflective": it.reflective,
                "low_contrast": it.low_contrast, "movable": it.movable,
                "present": it.present,
            }
            for it in sg.items
        ],
        "robot": [sg.robot[0], sg.robot[1]],
        "target": sg.target,
        "lighting": round(sg.lighting, 3),
        "clutter": sg.clutter,
    }


class CachedProposal:
    """Memoising wrapper around the campaign's proposal distribution.

    Campaign.p_fail_under computes `prior.log_pdf(t) - self.proposal.log_pdf(t)`
    for every stored theta. The proposal is a four-component mixture, so it is
    roughly four fifths of the cost, and it is recomputed from scratch on every
    archetype switch even though the thetas never change.

    Wrapping it here caches that term per theta. This changes no arithmetic:
    engine.py is untouched, the same MixtureProposal does the work, and
    selftest.py asserts the cached campaign returns bit-identical estimates to
    an uncached one. It just makes switching archetypes actually instant, which
    is the claim the UI makes.
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self._cache: Dict[int, float] = {}

    @property
    def name(self) -> str:
        return self.inner.name

    def sample(self, n_items: int, rng):
        return self.inner.sample(n_items, rng)

    def log_pdf(self, theta) -> float:
        key = id(theta)
        hit = self._cache.get(key)
        if hit is None:
            hit = self.inner.log_pdf(theta)
            self._cache[key] = hit
        return hit


def band(score: int) -> str:
    """Mirror of Campaign.readiness()'s banding, applied to a re-weighted estimate.

    engine.py does not export the thresholds and we do not modify it, so they
    are restated here. selftest.py asserts this function still agrees with
    Campaign.readiness() across the whole range, so it cannot drift silently.
    """
    return "READY" if score >= 85 else "MARGINAL" if score >= 60 else "NOT READY"


def rescore(camp: Campaign, prior) -> Dict[str, Any]:
    """Re-score an EXISTING campaign under a different prior. No new sampling.

    This is the whole point of importance re-weighting: the generations are
    already paid for, and moving to another archetype costs one pass over the
    stored thetas.
    """
    t0 = time.perf_counter()
    est, ess = camp.p_fail_under(prior)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    ok = bool(reliable(ess))
    score = int(round(100 * (1.0 - est)))
    return {
        "name": prior.name,
        "p_fail": round(est, 4),
        "ess": round(ess, 1),
        "reliable": ok,
        # Constraint 5: when the weights have degenerated these must not be
        # displayed as numbers. They are still sent so the UI can show what it
        # is withholding, but `reliable` is the gate and the UI greys them out.
        "score": score if ok else None,
        "state": band(score) if ok else None,
        "rescore_ms": round(elapsed_ms, 3),
        "samples_reused": len(camp.thetas),
        "new_samples": 0,
    }


def campaign_report(camp: Campaign, strategy: str, m: int, seed: int) -> Dict[str, Any]:
    """Everything the UI needs from one campaign. No new sampling happens here."""
    score, state = camp.readiness()
    # Warm the proposal log-pdf cache before timing anything. Filling it is part
    # of the campaign's own cost; charging it to the first archetype switch
    # would misreport what switching actually costs.
    first = next(iter(ARCHETYPES.values()))
    camp.p_fail_under(first)
    rows = [rescore(camp, prior) for prior in ARCHETYPES.values()]
    attribution = camp.attribution()
    total_fail = sum(attribution.values()) or 1
    return {
        "samples": m,
        "seed": seed,
        "strategy": strategy,
        "p_fail": round(camp.p_fail(), 4),
        "readiness": {"score": score, "state": state},
        "attribution": [
            {"object": k, "failures": v, "share": round(v / total_fail, 4)}
            for k, v in attribution.items()
        ],
        "archetypes": rows,
        "ess_min": engine.ESS_MIN,
        "proposal": camp.proposal.name,
    }


# ---------------------------------------------------------------------------
@dataclass
class Demo:
    """Single-session run state. This is a demo, not a service."""

    scene: SceneGraph = DEMO_ROOM
    strategy: str = "direct_approach"
    m: int = DEFAULT_M
    seed: int = DEFAULT_SEED
    campaign: Optional[Campaign] = None
    report: Optional[Dict[str, Any]] = None
    ledger: PrivacyLedger = field(default_factory=PrivacyLedger)
    provider: WorldModelProvider = field(default_factory=build_provider)
    history: List[float] = field(default_factory=list)   # readiness over time
    bandit: Optional[OnlineBandit] = None
    archetype: str = ""          # empty = show the proposal estimate
    sample_ms: float = 0.0

    def ensure_bandit(self) -> OnlineBandit:
        if self.bandit is None:
            self.bandit = OnlineBandit(self.scene, default_proposal(), seed=self.seed)
        return self.bandit

    def set_scene(self, scene: SceneGraph) -> None:
        """Adopt a new base room. The bandit model is kept deliberately: arm
        value is a function of the room context, and the context is exactly what
        changed, so the estimates transfer and the bars re-order."""
        self.scene = scene
        if self.bandit is not None:
            self.bandit.set_scene(scene)

    def run_campaign(self, strategy: Optional[str] = None) -> Dict[str, Any]:
        """Blocking. Call from a worker thread."""
        if strategy:
            self.strategy = strategy
        t0 = time.perf_counter()
        camp = Campaign(self.scene, CachedProposal(default_proposal())).run(
            self.m, self.strategy, self.seed)
        self.sample_ms = (time.perf_counter() - t0) * 1000.0
        self.campaign = camp
        # Building the report re-scores every archetype, which also warms the
        # proposal log-pdf cache, so later archetype switches are cheap.
        self.report = campaign_report(camp, self.strategy, self.m, self.seed)
        self.report["sample_ms"] = round(self.sample_ms, 1)
        self.history.append(self.report["readiness"]["score"])
        if len(self.history) > 200:
            self.history = self.history[-200:]
        return self.report

    def scene_payload(self) -> str:
        payload = json.dumps(scene_to_dict(self.scene), indent=2)
        self.ledger.note_payload(payload)
        return payload

    def state(self) -> Dict[str, Any]:
        return {
            "scene": scene_to_dict(self.scene),
            "strategies": list(STRATEGIES),
            "archetype_names": list(ARCHETYPES.keys()),
            "strategy": self.strategy,
            "samples": self.m,
            "seed": self.seed,
            "elite_k": ELITE_K,
            "report": self.report,
            "history": self.history,
            "privacy": self.ledger.to_dict(),
            "provider": self.provider.health(),
            "assertion": startup_assertion(),
            "ess_min": engine.ESS_MIN,
            "bandit": self.ensure_bandit().snapshot(),
            "archetype": self.archetype,
        }


DEMO = Demo()

app = FastAPI(title="Skopos", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    # Privacy assertion, one line, at startup. See privacy.py.
    log.info(startup_assertion())
    log.info("provider=%s samples=%d seed=%d", DEMO.provider.name, DEMO.m, DEMO.seed)
    # A scan would hand us frames here. We account for them and drop them.
    DEMO.ledger.note_frames(48)
    log.info("scan: %d frames processed in memory, %d retained",
             DEMO.ledger.frames_seen, DEMO.ledger.frames_retained)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def api_health() -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "provider": DEMO.provider.health(),
        "privacy": startup_assertion(),
        "samples_default": DEFAULT_M,
    })


@app.get("/api/campaign")
async def api_campaign(
    m: int = DEFAULT_M, strategy: str = "direct_approach", seed: int = DEFAULT_SEED
) -> JSONResponse:
    """Run a campaign and return readiness, p_fail and attribution.

    Runs on a worker thread: at ~6.4k samples/s a 20k campaign blocks for ~3s.
    """
    if strategy not in STRATEGIES:
        return JSONResponse({"error": "unknown strategy", "strategies": list(STRATEGIES)},
                            status_code=400)
    DEMO.m, DEMO.seed = max(100, min(m, 200_000)), seed
    report = await asyncio.to_thread(DEMO.run_campaign, strategy)
    return JSONResponse(report)


@app.get("/api/scene")
async def api_scene() -> JSONResponse:
    """The exact payload that would leave the device. Structured text, no pixels."""
    return JSONResponse(json.loads(DEMO.scene_payload()))


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# WebSocket: the live loop. Control messages up, state and frames down.
# ---------------------------------------------------------------------------
class Loop:
    def __init__(self, ws: WebSocket, demo: Demo) -> None:
        self.ws = ws
        self.d = demo
        self.closed = False
        self.busy = False
        self.bandit_on = True
        self.bandit_task: Optional[asyncio.Task] = None

    async def send(self, msg: Dict[str, Any]) -> None:
        if self.closed:
            return
        await self.ws.send_text(json.dumps(msg, separators=(",", ":")))

    async def send_state(self) -> None:
        await self.send({"type": "state", **self.d.state()})

    async def hello(self) -> None:
        await self.send({"type": "hello", "assertion": startup_assertion()})
        await self.send_state()
        self.bandit_task = asyncio.create_task(self.bandit_loop())

    async def bandit_loop(self) -> None:
        """Stream bandit value estimates continuously.

        Runs on the event loop rather than a worker thread: a tick is a handful
        of 5x5 matrix operations plus one surrogate call, microseconds, so it
        never blocks anything. The sleep is there for human eyes only.
        """
        ob = self.d.ensure_bandit()
        try:
            while not self.closed:
                if self.bandit_on and not self.busy:
                    last = None
                    for _ in range(BANDIT_TICKS_PER_FRAME):
                        last = ob.step()
                    snap = ob.snapshot()
                    await self.send({
                        "type": "bandit",
                        "bandit": snap,
                        "last": {
                            "arm": last.arm,
                            "reward": round(last.reward, 4),
                            "failed": last.failed,
                            "severity": round(last.severity, 3),
                            "culprit": last.culprit,
                        },
                    })
                await asyncio.sleep(BANDIT_INTERVAL_MS / 1000.0)
        except asyncio.CancelledError:
            pass

    async def run_campaign(self, strategy: Optional[str] = None) -> None:
        if self.busy:
            return
        self.busy = True
        try:
            await self.send({"type": "campaign_start", "samples": self.d.m,
                             "strategy": strategy or self.d.strategy})
            report = await asyncio.to_thread(self.d.run_campaign, strategy)
            payload = self.d.scene_payload()
            await self.render_base()
            await self.send({
                "type": "campaign_done",
                "report": report,
                "history": self.d.history,
                "scene": scene_to_dict(self.d.scene),
                "scene_payload": payload,
                "privacy": self.d.ledger.to_dict(),
            })
        finally:
            self.busy = False

    async def render_base(self) -> None:
        """Render the unperturbed room once, so the pane is never blank.

        The elite renders (the ones that matter) come from a separate stream.
        """
        sev, culprit = engine.surrogate(self.d.scene, self.d.strategy)
        frame = self.d.provider.render(self.d.scene, RenderRequest(
            seed=self.d.seed, step=0, severity=sev, culprit=culprit,
            strategy=self.d.strategy, status="running",
        ))
        await self.send({"type": "frame", "frame": frame.to_dict(),
                         "strategy": self.d.strategy, "label": "base room"})

    async def rescore(self, name: str) -> None:
        """Re-weight the existing campaign onto another archetype. No sampling."""
        camp = self.d.campaign
        if camp is None:
            await self.send({"type": "toast", "text": "run a campaign first"})
            return
        prior = ARCHETYPES.get(name)
        if prior is None:
            return
        self.d.archetype = name
        # Half a second of pure Python at 20k samples: off the event loop.
        row = await asyncio.to_thread(rescore, camp, prior)
        row["sample_ms"] = round(self.d.sample_ms, 1)
        await self.send({"type": "rescored", "row": row, "archetype": name})

    async def handle(self, msg: Dict[str, Any]) -> None:
        t = msg.get("type")
        if t == "run_campaign":
            strategy = msg.get("strategy")
            if strategy and strategy not in STRATEGIES:
                strategy = None
            if "samples" in msg:
                self.d.m = max(100, min(int(msg["samples"]), 200_000))
            if "seed" in msg:
                self.d.seed = int(msg["seed"])
            await self.run_campaign(strategy)
        elif t == "get_state":
            await self.send_state()
        elif t == "rescore":
            await self.rescore(msg.get("archetype", ""))
        elif t == "bandit_pause":
            self.bandit_on = False
        elif t == "bandit_resume":
            self.bandit_on = True
        elif t == "bandit_reset":
            self.d.bandit = None
            self.d.ensure_bandit()
            await self.send({"type": "toast", "text": "bandit reset — all four arms back to zero"})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    loop = Loop(ws, DEMO)
    await loop.hello()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await loop.handle(msg)
    except WebSocketDisconnect:
        pass
    finally:
        loop.closed = True
        if loop.bandit_task is not None:
            loop.bandit_task.cancel()

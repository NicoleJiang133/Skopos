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


def campaign_report(camp: Campaign, strategy: str, m: int, seed: int) -> Dict[str, Any]:
    """Everything the UI needs from one campaign. No new sampling happens here."""
    score, state = camp.readiness()
    rows = []
    for name, prior in ARCHETYPES.items():
        est, ess = camp.p_fail_under(prior)
        rows.append({
            "name": name,
            "p_fail": round(est, 4),
            "ess": round(ess, 1),
            # Constraint 5: the UI must never render an unreliable estimate as
            # if it were a number. This flag is the gate.
            "reliable": bool(reliable(ess)),
        })
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

    def run_campaign(self, strategy: Optional[str] = None) -> Dict[str, Any]:
        """Blocking. Call from a worker thread."""
        if strategy:
            self.strategy = strategy
        camp = Campaign(self.scene, default_proposal()).run(self.m, self.strategy, self.seed)
        self.campaign = camp
        self.report = campaign_report(camp, self.strategy, self.m, self.seed)
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

    async def send(self, msg: Dict[str, Any]) -> None:
        if self.closed:
            return
        await self.ws.send_text(json.dumps(msg, separators=(",", ":")))

    async def send_state(self) -> None:
        await self.send({"type": "state", **self.d.state()})

    async def hello(self) -> None:
        await self.send({"type": "hello", "assertion": startup_assertion()})
        await self.send_state()

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

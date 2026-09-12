"""
Skopos server: FastAPI + a single WebSocket carrying the live loop.

Everything the UI shows comes down /ws. Control messages go back up the same
socket. There is one session; this is a demo, not a service.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .privacy import startup_assertion
from .providers.base import WorldModelProvider
from .recorder import Recorder, list_runs, replay_events
from .session import Session, SessionConfig

log = logging.getLogger("skopos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def build_provider(name: Optional[str] = None) -> WorldModelProvider:
    name = (name or os.getenv("SKOPOS_PROVIDER", "mock")).lower()
    if name == "reactor":
        from .providers.reactor import ReactorProvider
        return ReactorProvider()
    if name == "runware":
        from .providers.runware import RunwareProvider
        return RunwareProvider()
    from .providers.mock import MockProvider
    return MockProvider()


def build_perception(name: Optional[str] = None):
    name = (name or os.getenv("SKOPOS_PERCEPTION", "mock")).lower()
    if name == "claude":
        from .perception.claude_vlm import ClaudeVLMPerception
        return ClaudeVLMPerception()
    from .perception.mock import MockPerception
    return MockPerception()


app = FastAPI(title="Skopos", version="0.1.0")
SESSION = Session(provider=build_provider(), perception=build_perception(),
                  config=SessionConfig())


@app.on_event("startup")
async def _startup() -> None:
    log.info(startup_assertion())
    log.info("provider=%s perception=%s seed=%s",
             SESSION.provider.name, SESSION.perception.name, SESSION.config.seed)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
async def api_state() -> JSONResponse:
    return JSONResponse(SESSION.state())


@app.get("/api/runs")
async def api_runs() -> JSONResponse:
    return JSONResponse({"runs": list_runs()})


@app.get("/api/health")
async def api_health() -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "provider": SESSION.provider.health(),
        "perception": SESSION.perception.name,
        "privacy": startup_assertion(),
    })


class Loop:
    """Owns the send side of one websocket connection."""

    def __init__(self, ws: WebSocket, session: Session) -> None:
        self.ws = ws
        self.s = session
        self.running = True
        self.recorder: Optional[Recorder] = None
        self.replaying = False
        self.replay_id: Optional[str] = None
        self.closed = False

    async def send(self, msg: Dict[str, Any], record: bool = True) -> None:
        if self.recorder is not None and record:
            self.recorder.event(msg)
        await self.ws.send_text(json.dumps(msg, separators=(",", ":")))

    async def send_state(self) -> None:
        await self.send({"type": "state", **self.s.state()})

    # ------------------------------------------------------------- main loop
    async def run(self) -> None:
        await self.send({"type": "hello", "assertion": startup_assertion()})
        await self.send_state()
        while not self.closed:
            if self.replaying:
                await asyncio.sleep(0.05)
                continue
            if not self.running:
                await asyncio.sleep(0.08)
                continue
            await self.attempt()

    async def attempt(self) -> None:
        s = self.s
        res = s.step()
        ep = res["episode"]
        n = s.config.frames_per_attempt
        payload = s.scene_payload()

        await self.send({
            "type": "attempt_start",
            "attempt": s.attempt_index,
            "arm": ep.arm,
            "p_success": round(ep.p_success, 4),
            "room": s.current.to_dict(),
            "scene_payload": payload,
            "scene_payload_bytes": len(payload.encode("utf-8")),
        })

        for i in range(n):
            if self.closed:
                return
            frac = (i + 1) / n
            frame = s.render(ep, frac, step=s.attempt_index * n + i)
            await self.send({"type": "frame", "frame": frame.to_dict(), "frac": round(frac, 3)})
            await asyncio.sleep(s.config.frame_interval_ms / 1000.0)

        await self.send({
            "type": "attempt_end",
            "attempt": s.attempt_index,
            "episode": ep.to_dict(),
            "bandit": s.bandit.snapshot(res["context"]),
            "metrics": s.metrics.to_dict(),
            "privacy": s.ledger.to_dict(),
            "room_attempts": s.room_attempts,
        })

    # -------------------------------------------------------------- controls
    async def handle(self, msg: Dict[str, Any]) -> None:
        s = self.s
        t = msg.get("type")

        if t == "pause":
            self.running = False
        elif t == "resume":
            self.running = True
        elif t == "set_rates":
            s.set_rates(msg.get("rates", {}))
            await self.send_state()
        elif t == "set_tilt":
            s.set_tilt(msg.get("tilt", 0.3))
            await self.send_state()
        elif t == "set_speed":
            s.config.frame_interval_ms = max(10, min(400, int(msg.get("ms", 70))))
        elif t == "set_resample":
            s.config.resample_every = max(1, min(50, int(msg.get("every", 8))))
            await self.send_state()
        elif t == "shift_room":
            s.shift_room()
            await self.send_state()
            await self.send({"type": "toast", "text": "room shifted — new sample drawn"})
        elif t == "reset":
            seed = msg.get("seed")
            s.reset(int(seed) if seed is not None else None)
            await self.send_state()
            await self.send({"type": "toast", "text": "session reset, seed " + str(s.config.seed)})
        elif t == "record_start":
            if self.recorder is None:
                self.recorder = Recorder()
                self.recorder.write_meta({
                    "seed": s.config.seed,
                    "provider": s.provider.name,
                    "perception": s.perception.name,
                    "prior": s.prior.to_dict(),
                    "config": {
                        "resample_every": s.config.resample_every,
                        "frames_per_attempt": s.config.frames_per_attempt,
                        "frame_interval_ms": s.config.frame_interval_ms,
                        "window": s.config.window,
                    },
                })
                await self.send({"type": "recording", "on": True, "run_id": self.recorder.run_id},
                                record=False)
        elif t == "record_stop":
            if self.recorder is not None:
                info = self.recorder.close(s.metrics.to_dict(), s.bandit.to_dict())
                self.recorder = None
                await self.send({"type": "recording", "on": False, "saved": info}, record=False)
        elif t == "list_runs":
            await self.send({"type": "runs", "runs": list_runs()}, record=False)
        elif t == "replay":
            asyncio.create_task(self.do_replay(msg.get("run_id", "")))
        elif t == "replay_stop":
            self.replaying = False

    async def do_replay(self, run_id: str) -> None:
        self.replaying = True
        self.replay_id = run_id
        try:
            await self.send({"type": "replay", "on": True, "run_id": run_id}, record=False)
            interval = self.s.config.frame_interval_ms / 1000.0
            for ev in replay_events(run_id):
                if not self.replaying or self.closed:
                    break
                ev = dict(ev)
                ev["_replay"] = True
                await self.ws.send_text(json.dumps(ev, separators=(",", ":")))
                if ev.get("type") == "frame":
                    await asyncio.sleep(interval)
        except FileNotFoundError as exc:
            await self.send({"type": "toast", "text": str(exc)}, record=False)
        finally:
            self.replaying = False
            await self.send({"type": "replay", "on": False, "run_id": run_id}, record=False)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    loop = Loop(ws, SESSION)
    sender = asyncio.create_task(loop.run())
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
        loop.running = False
        sender.cancel()


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

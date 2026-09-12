"""
Reactor connectivity probe: `python scripts/reactor_probe.py`

Run this BEFORE wiring the demo to a live model. It answers, against your key
and your model, the three things that cannot be known from the SDK alone:

  1. does the key authenticate and the model connect?
  2. what commands does this model actually declare? (request_schema)
  3. do video frames arrive, at what size and what rate?

and, optionally, whether a reference image uploads and is accepted.

It writes no frames to disk unless you pass --save-frame, and it never prints
your API key.

Usage
-----
    set REACTOR_API_KEY=rk_...            # or put it in .env
    python scripts/reactor_probe.py
    python scripts/reactor_probe.py --model reactor/helios --seconds 15
    python scripts/reactor_probe.py --reference path\\to\\room.jpg
    python scripts/reactor_probe.py --save-frame probe.png
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_dotenv(path: Path) -> None:
    """Minimal .env reader so the probe matches how the app is configured."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def redact(key: str) -> str:
    if not key:
        return "(unset)"
    return key[:6] + "…" + key[-4:] if len(key) > 12 else "(set)"


async def main() -> int:
    ap = argparse.ArgumentParser(description="Probe a live Reactor model.")
    ap.add_argument("--model", default=os.getenv("REACTOR_MODEL", "reactor/helios"))
    ap.add_argument("--seconds", type=float, default=12.0,
                    help="how long to watch for frames")
    ap.add_argument("--prompt", default="A tidy living room, eye level, natural light.")
    ap.add_argument("--prompt-command", default=os.getenv("REACTOR_PROMPT_COMMAND", "set_prompt"))
    ap.add_argument("--start-command", default=os.getenv("REACTOR_START_COMMAND", "start"))
    ap.add_argument("--image-command", default=os.getenv("REACTOR_IMAGE_COMMAND", "set_image"))
    ap.add_argument("--image-field", default=os.getenv("REACTOR_IMAGE_FIELD", "image"))
    ap.add_argument("--reference", action="append", default=[],
                    help="reference image to upload (repeatable). NOTE: uploads pixels.")
    ap.add_argument("--image-strength", type=float, default=None,
                    help="0-1. 1.0 locks the first frame to the reference; low values "
                         "let the prompt drive appearance while the image nudges layout.")
    ap.add_argument("--save-frame", default=None, help="write one received frame here")
    ap.add_argument("--schema-out", default=None, help="write the full schema JSON here")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.getenv("REACTOR_API_KEY", "")
    api_url = os.getenv("REACTOR_API_URL", "https://api.reactor.inc")

    print("=" * 70)
    print("Reactor probe")
    print("  model   :", args.model)
    print("  api_url :", api_url)
    print("  api_key :", redact(api_key))
    print("=" * 70)

    if not api_key:
        print("\nFAIL: REACTOR_API_KEY is not set.")
        print("      Put it in .env (which is gitignored) as REACTOR_API_KEY=rk_...")
        return 2

    try:
        from reactor_sdk import Reactor, ReactorStatus, TrackKind
    except ImportError:
        print("\nFAIL: reactor-sdk is not installed.")
        print("      pip install -r requirements-reactor.txt")
        return 2

    frames = {"n": 0, "first_at": None, "last": None, "shape": None}
    statuses = []

    reactor = Reactor(model_name=args.model, api_key=api_key, api_url=api_url)

    @reactor.on_status
    def _status(status):
        statuses.append(str(status))
        print("  status ->", status)

    @reactor.on_error
    def _err(err):
        print("  ERROR  ->", err)

    @reactor.on_track
    def _track(track):
        print("  track  -> name={!r} kind={} direction={}".format(
            track.name, track.kind, track.direction))
        if str(track.kind) != str(TrackKind.VIDEO):
            return

        @track.on_frame
        def _frame(frame):
            if frames["n"] == 0:
                frames["first_at"] = time.time()
                try:
                    frames["shape"] = tuple(frame.shape)
                except Exception:
                    frames["shape"] = type(frame).__name__
                print("  frame  -> first frame, shape={}".format(frames["shape"]))
            frames["n"] += 1
            frames["last"] = frame

    # ---- connect -----------------------------------------------------------
    print("\n[1/4] connecting…")
    t0 = time.time()
    try:
        await reactor.connect()
    except Exception as exc:
        print("\nFAIL: connect() raised {}: {}".format(type(exc).__name__, exc))
        print("      Check the model slug and that the key has access to it.")
        return 1
    print("      connected in {:.2f}s, status={}".format(time.time() - t0, reactor.status))

    # ---- schema ------------------------------------------------------------
    print("\n[2/4] request_schema() — the model's OWN command list")
    schema = None
    try:
        schema = await reactor.request_schema()
    except Exception as exc:
        print("      request_schema() raised {}: {}".format(type(exc).__name__, exc))
    if schema:
        paths = schema.get("paths", schema)
        names = sorted(paths.keys()) if isinstance(paths, dict) else []
        print("      commands ({}):".format(len(names)))
        for n in names:
            print("        -", n)
        if args.schema_out:
            Path(args.schema_out).write_text(json.dumps(schema, indent=2), encoding="utf-8")
            print("      full schema written to", args.schema_out)
        else:
            print("      (pass --schema-out schema.json for the full document)")
        print("\n      >>> Set these in .env to match what you see above:")
        print("          REACTOR_PROMPT_COMMAND / REACTOR_PROMPT_FIELD")
        print("          REACTOR_IMAGE_COMMAND  / REACTOR_IMAGE_FIELD")
        print("          REACTOR_START_COMMAND")

    # ---- reference images --------------------------------------------------
    print("\n[3/4] reference images")
    if not args.reference:
        print("      none given — nothing uploaded, no pixels left this machine")
    else:
        print("      NOTE: uploading photographs sends pixels to Reactor and breaks")
        print("            the 'no pixels leave the device' claim. Opt-in on purpose.")
        refs = []
        for path in args.reference:
            if not os.path.exists(path):
                print("      missing, skipped:", path)
                continue
            try:
                ref = await reactor.upload_file(path)
                refs.append(ref)
                print("      uploaded:", path, "->", type(ref).__name__)
            except Exception as exc:
                print("      upload FAILED for {}: {}: {}".format(path, type(exc).__name__, exc))
        if refs:
            data = {args.image_field: refs[0]} if len(refs) == 1 else {args.image_field: refs}
            try:
                reply = await reactor.send_command(args.image_command, data)
                print("      {} accepted, reply={}".format(args.image_command, reply))
            except Exception as exc:
                print("      {} FAILED: {}: {}".format(args.image_command, type(exc).__name__, exc))
                print("      -> check the schema above for the right command/field name")
            if args.image_strength is not None:
                try:
                    r = await reactor.send_command(
                        "set_image_strength", {"image_strength": args.image_strength})
                    print("      set_image_strength {} -> ok, reply={}".format(
                        args.image_strength, r))
                except Exception as exc:
                    print("      set_image_strength FAILED: {}: {}".format(
                        type(exc).__name__, exc))

    # ---- drive it and watch for frames -------------------------------------
    print("\n[4/4] sending prompt + start, watching {:.0f}s for frames…".format(args.seconds))
    for cmd, data in ((args.prompt_command, {"prompt": args.prompt}),
                      (args.start_command, {})):
        try:
            reply = await reactor.send_command(cmd, data)
            print("      {} -> ok, reply={}".format(cmd, reply))
        except Exception as exc:
            print("      {} FAILED: {}: {}".format(cmd, type(exc).__name__, exc))

    watch_start = time.time()
    await asyncio.sleep(args.seconds)
    elapsed = time.time() - watch_start

    print("\n" + "=" * 70)
    print("RESULT")
    print("  statuses seen :", " -> ".join(statuses) or "(none)")
    print("  frames        :", frames["n"])
    if frames["n"]:
        fps = frames["n"] / max(elapsed, 1e-6)
        print("  frame shape   :", frames["shape"])
        print("  rate          : {:.1f} fps over {:.1f}s".format(fps, elapsed))
        if args.save_frame and frames["last"] is not None:
            try:
                from PIL import Image
                Image.fromarray(frames["last"]).save(args.save_frame)
                print("  saved frame   :", args.save_frame)
            except Exception as exc:
                print("  could not save frame:", exc)
        print("\n  VERDICT: live streaming works. Set SKOPOS_PROVIDER=reactor.")
        ok = 0
    else:
        print("\n  VERDICT: connected but NO FRAMES arrived.")
        print("  Likely causes, in order:")
        print("    - the start command is named something else (see the schema above)")
        print("    - the model needs a prompt or an image before it will generate")
        print("    - the model is still warming up; try --seconds 30")
        ok = 1
    print("=" * 70)

    try:
        await reactor.disconnect()
    except Exception:
        pass
    return ok


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)

"""
Export the engine room as one standalone HTML file.

    python scripts/export_internals.py                     -> skopos-internals.html
    python scripts/export_internals.py --samples 20000 --out report.html

Runs a campaign, drives the bandit, runs the adversarial search, then bakes the
whole internals snapshot into `static/internals.html` as `window.__SKOPOS_DATA__`.
The result is a single file that opens in any browser with every chart intact,
makes no network requests and needs no server. It is a shareable artefact of one
specific run, seed included.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Export the engine room as one HTML file.")
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20260912)
    ap.add_argument("--strategy", default="direct_approach")
    ap.add_argument("--bandit-steps", type=int, default=900)
    ap.add_argument("--no-cem", action="store_true")
    ap.add_argument("--out", default="skopos-internals.html")
    args = ap.parse_args()

    # The exporter renders nothing through a provider, so keep it offline
    # regardless of what .env selects for the live demo.
    os.environ.setdefault("SKOPOS_PROVIDER", "mock")
    os.environ["SKOPOS_PROVIDER"] = "mock"

    import app
    import internals

    demo = app.Demo()
    demo.m, demo.seed, demo.strategy = args.samples, args.seed, args.strategy

    print("running campaign: {:,} samples, seed {}, strategy {}".format(
        args.samples, args.seed, args.strategy))
    t0 = time.perf_counter()
    report = demo.run_campaign(args.strategy)
    print("  {:.2f}s -> readiness {} {}, P(fail) {:.4f}".format(
        time.perf_counter() - t0,
        report["readiness"]["score"], report["readiness"]["state"], report["p_fail"]))

    print("driving the bandit: {} pulls".format(args.bandit_steps))
    ob = demo.ensure_bandit()
    for _ in range(args.bandit_steps):
        ob.step()
    lead = max(ob.snapshot()["arms"], key=lambda a: a["ucb"])
    print("  leading arm: {} (ucb {:.3f})".format(lead["name"], lead["ucb"]))

    if not args.no_cem:
        print("running the adversarial search")
        cem = demo.run_cem()
        print("  failure rate {:.0%} -> {:.0%}, light_mean {:.2f} -> {:.2f}".format(
            cem["iterations"][0], cem["iterations"][-1],
            cem["start_proposal"]["light_mean"], cem["final_proposal"]["light_mean"]))

    # The scan accounting the privacy panel reports.
    demo.ledger.note_frames(48)
    demo.scene_payload()

    print("building the snapshot")
    data = internals.snapshot(demo)

    tpl = (ROOT / "static" / "internals.html").read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"))
    # </script> inside a JSON string would end the block early.
    payload = payload.replace("</", "<\\/")
    banner = (
        "<!-- Skopos engine room — standalone export.\n"
        "     seed {seed} · {n:,} samples · strategy {strategy}\n"
        "     generated {when}\n"
        "     Self-contained: no server, no network, no external resources. -->\n"
    ).format(seed=args.seed, n=args.samples, strategy=args.strategy,
             when=time.strftime("%Y-%m-%d %H:%M:%S"))

    inject = "<script>window.__SKOPOS_DATA__ = {};</script>\n".format(payload)
    if "</head>" in tpl:
        html = banner + tpl.replace("</head>", inject + "</head>", 1)
    else:
        html = banner + inject + tpl

    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    kb = len(html.encode("utf-8")) / 1024
    print("\nwrote {} ({:.0f} KB, self-contained)".format(out.resolve(), kb))
    return 0


if __name__ == "__main__":
    sys.exit(main())

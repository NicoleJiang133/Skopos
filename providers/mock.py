"""
Mock world-model provider — the zero-API-key path. Build this first, keep it working.

Renders the scene graph as a stylised plan view (SVG, so no image libraries) and
applies a synthetic degradation curve as surrogate severity rises: blur, grain,
desaturation and darkening increase, mimicking how a real generative renderer
loses fidelity on out-of-distribution scenes.

This is NOT a world model. It is a deterministic stand-in with the same
interface, so the whole app runs end to end with no keys and no network.
"""
from __future__ import annotations

import base64
import math
import time
from typing import List, Tuple

from engine import Item, SceneGraph

from .base import Frame, RenderRequest, WorldModelProvider

W, H = 720, 480
# Room extent in metres, mapped into the canvas. DEMO_ROOM lives in roughly
# x in [0, 3], y in [0, 2.5], with the robot at the origin.
XMIN, XMAX = -0.45, 3.45
YMIN, YMAX = -0.45, 2.60


def _to_px(x: float, y: float) -> Tuple[float, float]:
    px = (x - XMIN) / (XMAX - XMIN) * W
    py = H - (y - YMIN) / (YMAX - YMIN) * H
    return px, py


def _scale() -> float:
    return W / (XMAX - XMIN)


def degradation(severity: float) -> dict:
    """Synthetic degradation curve.

    A saturating exponential d = 1 - exp(-k*s) on severity normalised by the
    surrogate's failure threshold. Fidelity falls fast at low severity then
    plateaus, which is roughly how generative renderers behave as a scene drifts
    off-distribution: the first perturbation hurts most.
    """
    s = max(0.0, min(severity / 2.5, 1.0))
    d = 1.0 - math.exp(-2.3 * s)
    return {
        "d": d,
        "blur_px": 2.4 * d,
        "grain": 0.5 * d,
        "saturation": 1.0 - 0.7 * d,
        "brightness": 1.0 - 0.3 * d,
        "fidelity": round(1.0 - d, 3),
    }


def _item_svg(it: Item, culprit: bool) -> str:
    s = _scale()
    r = max(it.radius * s, 5)
    px, py = _to_px(it.x, it.y)
    if it.reflective:
        fill, stroke = "#2e4a55", "#6fd4e8"
    elif it.low_contrast:
        fill, stroke = "#15181d", "#4b525c"
    elif not it.movable:
        fill, stroke = "#3f4a5a", "#6f7684"
    else:
        fill, stroke = "#5a5040", "#9a8a6a"
    if culprit:
        stroke = "#e0574a"
    label = it.name.replace("_", " ")
    return (
        '<g><circle cx="{:.1f}" cy="{:.1f}" r="{:.1f}" fill="{}" fill-opacity="0.75" '
        'stroke="{}" stroke-width="{}"/>'
        '<text x="{:.1f}" y="{:.1f}" font-size="11" fill="#9aa3b2" text-anchor="middle" '
        'font-family="ui-monospace,monospace">{}</text></g>'
    ).format(px, py, r, fill, stroke, 3 if culprit else 1.6, px, py + r + 13, label)


def _svg(sg: SceneGraph, req: RenderRequest, deg: dict) -> str:
    p: List[str] = []
    p.append('<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" '
             'viewBox="0 0 {} {}">'.format(W, H, W, H))
    p.append(
        "<defs>"
        '<filter id="deg" x="-10%" y="-10%" width="120%" height="120%">'
        '<feGaussianBlur stdDeviation="{:.2f}"/>'
        '<feColorMatrix type="saturate" values="{:.2f}"/>'
        '<feComponentTransfer><feFuncR type="linear" slope="{:.2f}"/>'
        '<feFuncG type="linear" slope="{:.2f}"/><feFuncB type="linear" slope="{:.2f}"/>'
        "</feComponentTransfer></filter>"
        '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" '
        'numOctaves="2" seed="{}"/><feColorMatrix type="saturate" values="0"/>'
        '<feComponentTransfer><feFuncA type="linear" slope="{:.2f}"/>'
        "</feComponentTransfer></filter></defs>".format(
            deg["blur_px"], deg["saturation"], deg["brightness"], deg["brightness"],
            deg["brightness"], req.seed % 1000, deg["grain"])
    )

    bg = int(10 + 24 * sg.lighting)
    p.append('<rect width="{}" height="{}" fill="rgb({},{},{})"/>'.format(W, H, bg, bg + 2, bg + 5))
    p.append('<g filter="url(#deg)">')
    p.append('<rect x="6" y="6" width="{}" height="{}" rx="8" fill="#161a20" '
             'stroke="#242a33"/>'.format(W - 12, H - 12))

    # half-metre grid
    x = 0.0
    while x <= 3.5:
        px, _ = _to_px(x, 0.0)
        p.append('<line x1="{:.0f}" y1="6" x2="{:.0f}" y2="{}" stroke="#1e242c"/>'.format(px, px, H - 6))
        x += 0.5
    y = 0.0
    while y <= 2.5:
        _, py = _to_px(0.0, y)
        p.append('<line x1="6" y1="{:.0f}" x2="{}" y2="{:.0f}" stroke="#1e242c"/>'.format(py, W - 6, py))
        y += 0.5

    # unmodelled clutter: objects that were never in the scan, drawn as ghosts
    if sg.clutter:
        for i in range(min(sg.clutter, 14)):
            a = 2.399963 * i           # golden-angle scatter, deterministic
            cx = 1.6 + 1.25 * math.cos(a) * ((i % 5) + 1) / 5.0
            cy = 1.2 + 1.05 * math.sin(a) * ((i % 4) + 1) / 4.0
            qx, qy = _to_px(cx, cy)
            p.append('<circle cx="{:.0f}" cy="{:.0f}" r="9" fill="none" stroke="#6f7684" '
                     'stroke-dasharray="3 3" stroke-width="1.2"/>'.format(qx, qy))

    target = sg.get(sg.target)
    rx, ry = _to_px(*sg.robot)
    if target is not None:
        tx, ty = _to_px(target.x, target.y)
        colour = {"fail": "#e0574a", "success": "#3ddc97"}.get(req.status, "#4aa8e0")
        p.append('<line x1="{:.1f}" y1="{:.1f}" x2="{:.1f}" y2="{:.1f}" stroke="{}" '
                 'stroke-width="2" stroke-opacity="0.75" stroke-dasharray="6 4"/>'.format(
                     rx, ry, tx, ty, colour))

    for it in sg.items:
        if not it.present:
            continue
        p.append(_item_svg(it, culprit=(req.culprit == it.name)))

    # missing objects, shown as an outline where they used to be
    for it in sg.items:
        if it.present:
            continue
        px, py = _to_px(it.x, it.y)
        r = max(it.radius * _scale(), 5)
        p.append('<circle cx="{:.1f}" cy="{:.1f}" r="{:.1f}" fill="none" stroke="#e0574a" '
                 'stroke-width="1.4" stroke-dasharray="4 4"/>'.format(px, py, r))
        p.append('<text x="{:.1f}" y="{:.1f}" font-size="10" fill="#e0574a" '
                 'text-anchor="middle" font-family="ui-monospace,monospace">{} gone</text>'.format(
                     px, py + r + 13, it.name.replace("_", " ")))

    p.append('<circle cx="{:.1f}" cy="{:.1f}" r="10" fill="#4aa8e0" fill-opacity="0.25" '
             'stroke="#4aa8e0" stroke-width="2"/>'.format(rx, ry))
    p.append('<text x="{:.1f}" y="{:.1f}" font-size="10" fill="#4aa8e0" text-anchor="middle" '
             'font-family="ui-monospace,monospace">robot</text>'.format(rx, ry + 24))
    p.append("</g>")

    if deg["grain"] > 0.01:
        p.append('<rect width="{}" height="{}" filter="url(#grain)" opacity="0.5"/>'.format(W, H))

    p.append('<text x="12" y="22" font-size="11" fill="#7c8595" font-family="ui-monospace,monospace">'
             'MOCK RENDER / synthetic / not a world model / fidelity {:.2f}</text>'.format(
                 deg["fidelity"]))
    tail = "severity {:.2f}".format(req.severity)
    if req.of:
        tail = "elite {}/{} · ".format(req.rank + 1, req.of) + tail
    if req.culprit and req.culprit != "none":
        tail += " · culprit " + req.culprit
    p.append('<text x="12" y="{}" font-size="11" fill="#9aa3b2" '
             'font-family="ui-monospace,monospace">{}</text>'.format(H - 26, tail))
    p.append('<text x="12" y="{}" font-size="11" fill="#9aa3b2" '
             'font-family="ui-monospace,monospace">arm {} / light {:.2f} / clutter {}</text>'.format(
                 H - 11, req.strategy or "—", sg.lighting, sg.clutter))
    p.append("</svg>")
    return "".join(p)


class MockProvider(WorldModelProvider):
    name = "mock"
    live = False

    def render(self, sg: SceneGraph, req: RenderRequest) -> Frame:
        t0 = time.perf_counter()
        deg = degradation(req.severity)
        svg = _svg(sg, req, deg)
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return Frame(
            data_url="data:image/svg+xml;base64," + b64,
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            step=req.step,
            meta={"fidelity": deg["fidelity"], "severity": round(req.severity, 3),
                  "culprit": req.culprit, "live": False},
        )

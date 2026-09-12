"""
Mock world-model provider — the zero-API-key path. BUILD TARGET #1.

It renders the SceneGraph as a stylised plan view (SVG, so no image libraries)
and applies a *synthetic degradation curve* as perturbation severity rises:
blur, grain, desaturation and darkening increase, mimicking how a real
generative renderer loses fidelity on out-of-distribution scenes.

This is NOT a world model. It is a deterministic, seeded stand-in with the same
interface, so the whole app runs end to end with no keys and no network.
"""
from __future__ import annotations

import base64
import math
import time
from typing import List, Tuple

from ..scene_graph import SceneGraph, SceneObject
from .base import Frame, RenderRequest, WorldModelProvider

W, H = 760, 520
# Room extent in metres mapped into the canvas.
XMIN, XMAX = -0.8, 3.6
YMIN, YMAX = -1.6, 2.2

PALETTE = {
    "wood": "#6b5233", "fabric": "#3f4a5a", "ceramic": "#c8ccd4", "metal": "#8b93a1",
    "glass": "#2e4a55", "plastic": "#5a5f4a", "organic": "#3f6b3f", "paper": "#b8b09a",
    "unknown": "#555a63",
}


def _to_px(x: float, y: float) -> Tuple[float, float]:
    px = (x - XMIN) / (XMAX - XMIN) * W
    py = H - (y - YMIN) / (YMAX - YMIN) * H
    return px, py


def _scale() -> Tuple[float, float]:
    return W / (XMAX - XMIN), H / (YMAX - YMIN)


def degradation(severity: float) -> dict:
    """The synthetic degradation curve.

    A saturating exponential: d = 1 - exp(-k * severity). Fidelity falls fast at
    low severity then plateaus, which is roughly how generative renderers behave
    when a scene drifts off-distribution — the first perturbation hurts most.
    k = 2.3 puts d ~= 0.9 at severity = 1.
    """
    k = 2.3
    d = 1.0 - math.exp(-k * max(0.0, min(1.0, severity)))
    return {
        "d": d,
        "blur_px": 2.6 * d,
        "grain": 0.55 * d,
        "saturation": 1.0 - 0.75 * d,
        "brightness": 1.0 - 0.35 * d,
        "fidelity": round(1.0 - d, 3),
    }


def _obj_svg(o: SceneObject, deg: dict) -> str:
    sx, sy = _scale()
    w = max(o.extent[0] * sx, 6)
    h = max(o.extent[1] * sy, 6)
    px, py = _to_px(o.pose.x, o.pose.y)
    fill = PALETTE.get(o.material, PALETTE["unknown"])
    stroke = "#e0574a" if o.hazard_flags else "#6f7684"
    dash = ' stroke-dasharray="4 3"' if "occluding" in o.hazard_flags else ""
    op = 0.55 + 0.45 * o.confidence
    rot = math.degrees(o.pose.yaw)
    return (
        '<g transform="translate({:.1f},{:.1f}) rotate({:.1f})">'
        '<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" rx="4" '
        'fill="{}" fill-opacity="{:.2f}" stroke="{}" stroke-width="1.6"{}/>'
        '<text x="0" y="{:.1f}" font-size="11" fill="#9aa3b2" text-anchor="middle" '
        'font-family="ui-monospace,monospace">{}</text></g>'
    ).format(px, py, rot, -w / 2, -h / 2, w, h, fill, op, stroke, dash,
             h / 2 + 12, o.label)


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

    light = sg.lighting.level
    bg = int(12 + 22 * light)
    p.append('<rect width="{}" height="{}" fill="rgb({},{},{})"/>'.format(W, H, bg, bg + 2, bg + 5))
    p.append('<g filter="url(#deg)">')
    p.append('<rect x="8" y="8" width="{}" height="{}" rx="8" fill="#161a20" '
             'stroke="#242a33"/>'.format(W - 16, H - 16))

    # 0.5 m grid
    x = XMIN
    while x < XMAX:
        px, _ = _to_px(x, 0.0)
        p.append('<line x1="{:.0f}" y1="8" x2="{:.0f}" y2="{}" stroke="#1e242c"/>'.format(px, px, H - 8))
        x += 0.5
    y = YMIN
    while y < YMAX:
        _, py = _to_px(0.0, y)
        p.append('<line x1="8" y1="{:.0f}" x2="{}" y2="{:.0f}" stroke="#1e242c"/>'.format(py, W - 8, py))
        y += 0.5

    if sg.lighting.glare > 0.02:
        gx, gy = _to_px(XMAX - 0.6, YMAX - 0.5)
        p.append('<circle cx="{:.0f}" cy="{:.0f}" r="{:.0f}" fill="#ffd9a0" '
                 'fill-opacity="{:.2f}"/>'.format(gx, gy, 90 + 140 * sg.lighting.glare,
                                                  0.10 + 0.32 * sg.lighting.glare))

    for o in sorted(sg.objects, key=lambda o: -(o.extent[0] * o.extent[1])):
        p.append(_obj_svg(o, deg))

    colour = {"success": "#3ddc97", "fail": "#e0574a"}.get(req.status, "#4aa8e0")
    if req.path:
        pts = " ".join("{:.1f},{:.1f}".format(*_to_px(q[0], q[1])) for q in req.path)
        p.append('<polyline points="{}" fill="none" stroke="{}" stroke-width="2.5" '
                 'stroke-opacity="0.9" stroke-linecap="round"/>'.format(pts, colour))
    if req.agent_xy:
        ax, ay = _to_px(req.agent_xy[0], req.agent_xy[1])
        p.append('<circle cx="{:.1f}" cy="{:.1f}" r="9" fill="{}" fill-opacity="0.25" '
                 'stroke="{}" stroke-width="2"/>'.format(ax, ay, colour, colour))
    p.append("</g>")

    if deg["grain"] > 0.01:
        p.append('<rect width="{}" height="{}" filter="url(#grain)" opacity="0.5"/>'.format(W, H))

    p.append('<text x="14" y="24" font-size="12" fill="#7c8595" font-family="ui-monospace,monospace">'
             'MOCK RENDER / synthetic / not a world model / fidelity {:.2f} / seed {} / step {}'
             "</text>".format(deg["fidelity"], req.seed, req.step))
    if req.strategy:
        tail = "  hazard: " + req.hazard_hit if req.hazard_hit else ""
        p.append('<text x="14" y="{}" font-size="12" fill="#9aa3b2" '
                 'font-family="ui-monospace,monospace">arm: {}{}</text>'.format(H - 14, req.strategy, tail))
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
            meta={"fidelity": deg["fidelity"], "severity": round(req.severity, 3)},
        )

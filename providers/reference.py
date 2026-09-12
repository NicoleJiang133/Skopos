"""
Rendered reference images — layout conditioning without sending a photograph.

WHY THIS EXISTS
---------------
A world model conditioned on text alone throws away the geometry the surrogate
actually scores on. The obvious fix is to hand it a reference image of the room.
The obvious way to get one — photograph the real room — sends pixels to a third
party and destroys Skopos's headline privacy claim.

So we draw the reference instead. The image produced here is a **pure function
of the SceneGraph**, and the SceneGraph is already the one artefact that leaves
the device. It therefore discloses nothing that was not already disclosed: no
camera ever contributed to it, and you could reconstruct it from the JSON in the
privacy panel with a pencil and a ruler.

That is the whole argument, and it is worth being precise about it rather than
waving at "synthetic": uploading this is not a weaker version of uploading a
photo, it is a different thing. Zero additional information crosses the boundary.

WHAT IT DRAWS
-------------
A clean overhead plan of the room: floor, the robot, the target, each object as
a filled disc sized by its real radius, tinted by what the engine cares about
(reflective, low-contrast, fixed), plus the robot-to-target line. It is drawn
larger and cleaner than the mock provider's debug view, with no HUD text, since
this is conditioning input rather than something a human reads.

Pillow only — no SVG rasteriser, no headless browser.
"""
from __future__ import annotations

import io
import math
from typing import Optional, Tuple

from engine import Item, SceneGraph

# Room extent in metres mapped into the image, matching the mock renderer.
XMIN, XMAX = -0.45, 3.45
YMIN, YMAX = -0.45, 2.60

# Palette chosen so the distinctions the engine reasons about survive being
# resized and re-encoded: reflective reads cold and bright, low-contrast reads
# near-black, fixed furniture reads muted.
FLOOR = (28, 26, 24)
WALL = (46, 43, 40)
C_REFLECTIVE = (150, 205, 225)
C_LOW_CONTRAST = (16, 16, 18)
C_FIXED = (96, 92, 86)
C_MOVABLE = (168, 140, 96)
C_TARGET = (236, 232, 224)
C_ROBOT = (90, 170, 220)


def _project(x: float, y: float, w: int, h: int, pad: int) -> Tuple[float, float]:
    px = pad + (x - XMIN) / (XMAX - XMIN) * (w - 2 * pad)
    py = (h - pad) - (y - YMIN) / (YMAX - YMIN) * (h - 2 * pad)
    return px, py


def _colour(it: Item, target: str) -> Tuple[int, int, int]:
    if it.name == target:
        return C_TARGET
    if it.reflective:
        return C_REFLECTIVE
    if it.low_contrast:
        return C_LOW_CONTRAST
    return C_FIXED if not it.movable else C_MOVABLE


def _shade(rgb: Tuple[int, int, int], f: float) -> Tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def render_reference(
    scene: SceneGraph,
    size: Tuple[int, int] = (768, 768),
    label: bool = False,
) -> Optional[bytes]:
    """Draw the scene graph as a PNG layout reference. Returns None without Pillow.

    `label` is off by default: object names help a human read the image but are
    text a generative model may try to reproduce in the output.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    w, h = size
    pad = int(min(w, h) * 0.05)

    # Lighting scales the whole image: a dark room should look dark to the model.
    lit = 0.35 + 0.65 * max(0.0, min(1.0, scene.lighting))
    img = Image.new("RGB", (w, h), _shade(WALL, lit))
    d = ImageDraw.Draw(img, "RGBA")

    # floor
    fx0, fy0 = _project(XMIN, YMIN, w, h, pad)
    fx1, fy1 = _project(XMAX, YMAX, w, h, pad)
    d.rectangle([min(fx0, fx1), min(fy0, fy1), max(fx0, fx1), max(fy0, fy1)],
                fill=_shade(FLOOR, lit))

    # half-metre grid, faint: gives the model a sense of scale
    grid = _shade((70, 66, 62), lit) + (90,)
    x = 0.0
    while x <= 3.5:
        px, _ = _project(x, 0.0, w, h, pad)
        d.line([(px, min(fy0, fy1)), (px, max(fy0, fy1))], fill=grid, width=1)
        x += 0.5
    y = 0.0
    while y <= 2.5:
        _, py = _project(0.0, y, w, h, pad)
        d.line([(min(fx0, fx1), py), (max(fx0, fx1), py)], fill=grid, width=1)
        y += 0.5

    scale = (w - 2 * pad) / (XMAX - XMIN)

    # unmodelled clutter: faint ghosts, deterministic from the count alone
    for i in range(min(scene.clutter, 16)):
        a = 2.399963 * i
        cx = 1.6 + 1.2 * math.cos(a) * ((i % 5) + 1) / 5.0
        cy = 1.15 + 1.0 * math.sin(a) * ((i % 4) + 1) / 4.0
        px, py = _project(cx, cy, w, h, pad)
        r = 0.10 * scale
        d.ellipse([px - r, py - r, px + r, py + r],
                  outline=_shade((150, 146, 140), lit) + (130,), width=2)

    target = scene.get(scene.target)
    rx, ry = _project(scene.robot[0], scene.robot[1], w, h, pad)

    # the path the task has to take
    if target is not None:
        tx, ty = _project(target.x, target.y, w, h, pad)
        d.line([(rx, ry), (tx, ty)], fill=_shade(C_ROBOT, lit) + (110,), width=3)

    # Draw order matters. Floor coverings (a dark rug is low-contrast and fixed)
    # go down first, then everything else largest-first, so a rug cannot paint
    # over the reflective table that sits on top of it — which is exactly what
    # happened the first time this was drawn, hiding the room's worst hazard.
    def _layer(o: Item) -> tuple:
        floor_covering = o.low_contrast and not o.movable
        return (0 if floor_covering else 1, -o.radius)

    for it in sorted(scene.items, key=_layer):
        if not it.present:
            continue
        px, py = _project(it.x, it.y, w, h, pad)
        r = max(it.radius * scale, 5)
        col = _shade(_colour(it, scene.target), lit)
        flat = it.low_contrast and not it.movable
        if not flat:
            # soft contact shadow, so shapes read as objects rather than stickers
            d.ellipse([px - r * 1.12, py - r * 0.95 + r * 0.22,
                       px + r * 1.12, py + r * 1.05 + r * 0.22], fill=(0, 0, 0, 90))
        d.ellipse([px - r, py - r, px + r, py + r], fill=col)
        if it.reflective:
            d.ellipse([px - r, py - r, px + r, py + r],
                      outline=_shade((225, 245, 255), lit), width=max(2, int(r * 0.10)))
            d.ellipse([px - r * 0.45, py - r * 0.55, px - r * 0.05, py - r * 0.15],
                      fill=(255, 255, 255, 120))
        if label:
            d.text((px + r + 6, py - 6), it.name.replace("_", " "),
                   fill=_shade((200, 200, 200), lit))

    # robot marker last, on top
    rr = max(0.16 * scale, 8)
    d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr],
              outline=_shade(C_ROBOT, lit), width=max(3, int(rr * 0.22)))
    d.ellipse([rx - rr * 0.35, ry - rr * 0.35, rx + rr * 0.35, ry + rr * 0.35],
              fill=_shade(C_ROBOT, lit))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def describe(scene: SceneGraph) -> str:
    """One line naming what the reference encodes, for logs and the UI."""
    present = sum(1 for it in scene.items if it.present)
    return ("rendered from the scene graph: {} objects, lighting {:.2f}, "
            "clutter {} — derived, not photographed".format(
                present, scene.lighting, scene.clutter))

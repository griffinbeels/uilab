"""Contact sheets: the same thing, at every width, in one image.

The gates in this module answer "is something broken" and are deliberately
blind to "does this read as the thing you meant". A screenshot answers the
second question and nothing else does — which matters most DURING
implementation, not after:

    "for most features while you're implementing, you could probably solve a
    lot of your bugs by simply taking screenshots and going 'oh... there's only
    one rank standard' while you're thinking, or 'oh, UI elements are
    intersecting, weird...'"  (2026-07-29)

Both of those examples are real and both cost days. A fixture seeded a star
with one strategy, so the card drew ONE rank banner instead of two and the
entire class of two-banner defects was unmeasurable — a single glance at a shot
of that card would have said so. And two banner washes overlapped by 15px at
every stacked width while four DOM probes reported the page clean.

This is a review aid, never a gate. It has no baseline and nothing to maintain,
which is exactly why it does not flake and does not need managing.
"""
from __future__ import annotations

import io
from pathlib import Path

from uilab.driver import get_driver
from uilab.project import Project, Story

# A clip is taken around the element, not tight to it: a decoration that has
# escaped its box is the thing you are most often looking for, and a tight crop
# is the one framing guaranteed to cut it off.
BLEED = 12


def _clip_rect(page, selector: str) -> dict | None:
    return page.evaluate("""
      (() => {
        const el = document.querySelector(%r);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return null;
        return JSON.stringify({
          x: Math.max(0, r.left - %d), y: Math.max(0, r.top - %d),
          width: Math.min(innerWidth, r.width + %d),
          height: r.height + %d});
      })()
    """ % (selector, BLEED, BLEED, BLEED * 2, BLEED * 2))


def shoot(project: Project, widths, selector: str | None = None,
          height: int = 1100, story: Story | None = None,
          driver_name: str | None = None, settle_ms: int = 450):
    """Render at each width and return [(label, png_bytes), ...].

    `selector` crops to one element — the usual case, since a whole-page shot
    at eight widths is mostly chrome you are not looking at. A width where the
    element does not exist is reported as such rather than skipped: "it is not
    on the page at 320px" is frequently the answer you needed.
    """
    import json
    import time

    shots: list[tuple[str, bytes]] = []
    with project.open() as url, get_driver(driver_name).launch() as page:
        page.goto(url)
        if project.ready_selector:
            page.wait_for(project.ready_selector)
        for width in widths:
            page.set_viewport(width, height)
            time.sleep(settle_ms / 1000)
            if story is not None and story.setup:
                page.evaluate(story.setup)
                time.sleep(settle_ms / 1000)
            clip = None
            if selector:
                raw = _clip_rect(page, selector)
                if not raw:
                    shots.append((f"{width}px — NOT PRESENT", b""))
                    continue
                clip = json.loads(raw)
            shots.append((f"{width}px", page.screenshot(clip=clip)))
    return shots


def compose(shots, max_height: int = 1000, gap: int = 14,
            label_height: int = 20, background=(12, 18, 28)) -> bytes:
    """Lay the shots out in one row, labelled, and return PNG bytes.

    One row on purpose: the whole point is comparing the SAME surface across
    widths, and a grid puts the comparison on two axes when there is only one.
    """
    from PIL import Image, ImageDraw

    tiles = []
    for label, data in shots:
        if not data:
            tiles.append((label, None))
            continue
        image = Image.open(io.BytesIO(data)).convert("RGB")
        if image.height > max_height:
            scale = max_height / image.height
            image = image.resize((max(1, round(image.width * scale)), max_height))
        tiles.append((label, image))

    widths = [tile.width if tile else 140 for _, tile in tiles]
    heights = [tile.height if tile else 40 for _, tile in tiles]
    sheet = Image.new(
        "RGB",
        (sum(widths) + gap * (len(tiles) + 1),
         max(heights) + label_height + gap * 2),
        background)
    draw = ImageDraw.Draw(sheet)
    x = gap
    for (label, tile), width in zip(tiles, widths):
        draw.text((x, gap // 2), label, fill=(220, 228, 240))
        if tile is not None:
            sheet.paste(tile, (x, gap + label_height))
        else:
            draw.text((x, gap + label_height), "(absent)", fill=(220, 120, 120))
        x += width + gap
    out = io.BytesIO()
    sheet.save(out, format="PNG")
    return out.getvalue()


def write(path, project: Project, widths, **kwargs) -> Path:
    """shoot + compose + save. Returns the path, for printing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compose(shoot(project, widths, **kwargs)))
    return path

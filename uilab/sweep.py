"""Run the matrix: every viewport x every story, collecting layout defects.

The matrix is DERIVED from the stylesheet's own declared thresholds, with a
probe point on BOTH sides of each. A threshold is the only place a layout can
newly break, and hand-picking three sample widths is how a set of rank banners
passed at 1400/900/700 while every window from ~1101px to ~1500px was broken.
"""
from __future__ import annotations

import time
from collections import namedtuple
from pathlib import Path

from uilab import css
from uilab.driver import get_driver
from uilab.project import Project, Story

Viewport = namedtuple("Viewport", "width height label")

PROBE_JS = (Path(__file__).parent / "probes.js").read_text(encoding="utf-8")

# WCAG 1.4.10 Reflow: content must reflow at 320 CSS px with no two-dimensional
# scrolling. An objective floor, rather than a number somebody invented.
WCAG_REFLOW = Viewport(320, 800, "wcag-reflow")

DEFAULT_POINTS = (WCAG_REFLOW, Viewport(1920, 1080, "desktop"),
                  Viewport(1280, 720, "short-window"))


def derived_matrix(project: Project) -> list[Viewport]:
    """Both sides of every declared threshold, plus the project's own points."""
    points: dict[tuple[int, int], Viewport] = {
        (v.width, v.height): v for v in DEFAULT_POINTS}
    for width, height in project.extra_viewports:
        points[(width, height)] = Viewport(width, height, f"{width}x{height}")
    if project.stylesheet:
        text = css.stylesheet_text(project.stylesheet)
        for block in css.size_blocks(css.parse_blocks(text)):
            for name, value in css.thresholds(block):
                for edge in (value, value + 1):
                    key = (edge, 1000) if name.endswith("width") else (1400, edge)
                    label = f"{'w' if name.endswith('width') else 'h'}{value}"
                    points.setdefault(key, Viewport(key[0], key[1], label))
    return sorted(points.values(), key=lambda v: (-v.width, -v.height))


def _probe(page, story: Story | None, project: Project) -> dict:
    config = {"at": story.at if story else "",
              "neverTruncate": list(project.never_truncate)}
    import json
    return page.evaluate(f"(__uilab({json.dumps(config)}))")


def run(project: Project, viewports: list[Viewport] | None = None,
        driver_name: str | None = None, settle_ms: int = 320,
        shots: bool = False) -> dict:
    """Sweep and return {defects, viewports, stories, shots}."""
    viewports = viewports or derived_matrix(project)
    stories = list(project.stories) or [None]
    defects: dict[str, str] = {}
    images: list[tuple[str, bytes]] = []

    with project.open() as url, get_driver(driver_name).launch() as page:
        page.goto(url)
        if project.ready_selector:
            page.wait_for(project.ready_selector)
        time.sleep(settle_ms / 1000)
        for view in viewports:
            page.set_viewport(view.width, view.height)
            time.sleep(settle_ms / 1000)
            page.evaluate(PROBE_JS)
            for story in stories:
                if story is not None:
                    if story.skip_if and page.evaluate(f"({story.skip_if})"):
                        continue
                    if story.setup:
                        page.evaluate(story.setup)
                        time.sleep(settle_ms / 1000)
                        page.evaluate(PROBE_JS)
                result = _probe(page, story, project)
                if isinstance(result, dict) and result.get("error"):
                    continue                    # story not applicable at this size
                label = story.name if story else "page"
                for kind in ("overflow", "clipped", "truncated", "overlap"):
                    for item in result.get(kind, []):
                        defects[f"{view.width}x{view.height} [{label}] {kind} :: "
                                f"{item['selector']}"] = item["detail"]
                if shots:
                    images.append((f"{view.width}x{view.height}-{label}",
                                   page.screenshot()))
    return {"defects": defects, "viewports": len(viewports),
            "stories": len(stories), "shots": images}


def new_defects(project: Project, result: dict) -> dict[str, str]:
    """Defects not already recorded in the project's known_defects."""
    return {key: detail for key, detail in result["defects"].items()
            if key not in project.known_defects}


def stale_exemptions(project: Project, result: dict) -> list[str]:
    """known_defects rows whose defect no longer occurs.

    A stale exemption is a lie about what is broken, and the list stops meaning
    anything the moment one is allowed to sit there.
    """
    return [key for key in project.known_defects if key not in result["defects"]]

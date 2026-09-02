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
from uilab.project import Project, Story, stylesheet_paths

Viewport = namedtuple("Viewport", "width height label")


def viewport_key(view: Viewport) -> str:
    """The prefix every defect key at this viewport starts with (`1920x1080`),
    and the id a per-viewport test case carries. One derivation, so the stale
    gate's per-viewport filter can never drift from the key builder."""
    return f"{view.width}x{view.height}"

PROBE_JS = (Path(__file__).parent / "probes.js").read_text(encoding="utf-8")

# WCAG 1.4.10 Reflow: content must reflow at 320 CSS px with no two-dimensional
# scrolling. An objective floor, rather than a number somebody invented.
WCAG_REFLOW = Viewport(320, 800, "wcag-reflow")

DEFAULT_POINTS = (WCAG_REFLOW, Viewport(1920, 1080, "desktop"),
                  Viewport(1280, 720, "short-window"))


def _candidate_matrix(project: Project) -> list[Viewport]:
    """Both sides of every declared threshold, plus the project's own points."""
    points: dict[tuple[int, int], Viewport] = {}
    if project.include_default_viewports:
        points.update({(view.width, view.height): view for view in DEFAULT_POINTS})
    for width, height in project.extra_viewports:
        points[(width, height)] = Viewport(width, height, f"{width}x{height}")
    for path in stylesheet_paths(project):
        text = css.stylesheet_text(path)
        for block in css.size_blocks(css.parse_blocks(text)):
            for name, value in css.thresholds(block):
                for edge in (value, value + 1):
                    key = (edge, 1000) if name.endswith("width") else (1400, edge)
                    label = f"{'w' if name.endswith('width') else 'h'}{value}"
                    points.setdefault(key, Viewport(key[0], key[1], label))
    return sorted(points.values(), key=lambda view: (-view.width, -view.height))


def derived_matrix(project: Project) -> list[Viewport]:
    """The candidate matrix, minus anything below the supported minimum width."""
    floor = project.min_viewport_width
    return [view for view in _candidate_matrix(project) if view.width >= floor]


def dropped_viewports(project: Project) -> list[Viewport]:
    """Widths the floor excluded — so a narrowed matrix is never silent.

    A sweep that stops measuring 14 widths and still says "0 defects" reads
    exactly like one that measures everything. Callers print this.
    """
    floor = project.min_viewport_width
    return [view for view in _candidate_matrix(project) if view.width < floor]


def _probe(page, story: Story | None, project: Project) -> dict:
    config = {"at": story.at if story else "",
              "neverTruncate": list(project.never_truncate),
              "mayClip": list(project.may_clip),
              "mayBleed": list(project.may_bleed)}
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
                    # The probe's only error is "scope selector matched
                    # nothing" (probes.js) -- a story whose `at` genuinely
                    # is not applicable at this viewport/state has `skip_if`
                    # for exactly that, checked and honoured BEFORE this call.
                    # Reaching here with an error means the Story's `at` is
                    # wrong for the state its own `setup`/`skip_if` just
                    # produced, which is a bug in the Story, not a legitimate
                    # skip -- silently `continue`-ing past it is what let a
                    # rewritten selector go on matching nothing at EVERY
                    # viewport, forever, three separate times in one
                    # consuming project (sm64_tracker, 2026-08-03) before
                    # anyone noticed the story had stopped measuring
                    # anything. Fail loudly instead: a scope that never
                    # matches is a broken gate, and a broken gate that
                    # reports "0 defects" is worse than no gate at all.
                    story_name = story.name if story else "page"
                    raise RuntimeError(
                        f"uilab story {story_name!r} at {view.width}x"
                        f"{view.height}: {result['error']} -- fix the "
                        "Story's `at` selector or its `skip_if`, don't "
                        "swallow the error")
                label = story.name if story else "page"
                for kind in ("overflow", "clipped", "truncated", "overlap",
                             "decoration"):
                    for item in result.get(kind, []):
                        defects[f"{viewport_key(view)} [{label}] {kind} :: "
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


def stale_exemptions(project: Project, result: dict,
                     viewport: Viewport | None = None) -> list[str]:
    """known_defects rows whose defect no longer occurs.

    A stale exemption is a lie about what is broken, and the list stops meaning
    anything the moment one is allowed to sit there.

    With a `viewport`, only the rows naming THAT viewport are judged: a
    per-viewport case's result holds nothing else, so judging every row
    against it would call every other viewport's exemption stale. The rows
    no per-viewport case can reach -- ones naming a viewport outside the
    matrix -- are `exemptions_outside_matrix`'s job.
    """
    rows = project.known_defects
    if viewport is not None:
        prefix = viewport_key(viewport) + " "
        rows = [key for key in rows if key.startswith(prefix)]
    return [key for key in rows if key not in result["defects"]]


def exemptions_outside_matrix(project: Project) -> list[str]:
    """known_defects rows naming a viewport the matrix does not contain.

    Browser-free. A whole-matrix sweep reports such a row stale for free; a
    per-viewport sweep never judges it at all, so this is the check that
    keeps the two shapes equally strict.
    """
    live = {viewport_key(view) for view in derived_matrix(project)}
    return [key for key in project.known_defects
            if key.split(" ", 1)[0] not in live]

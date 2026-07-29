"""The seam: what a project tells uilab about itself.

Everything uilab does is generic except five facts, and those five are the
whole per-project surface.  A consuming project writes ONE of these — usually
about twenty lines — and gets the sweep, the cascade helper, the story runner
and the pytest gates for free.

Keeping the seam this narrow is deliberate.  The point of the module is that
instrumentation improves in one place and every project gets it; that only
holds while a project cannot fork the behaviour, only describe itself.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Story:
    """One component in one declared state.

    The name is borrowed from Component Story Format, and so is the idea: a
    story DECLARES the state rather than hoping the data produces it.  That is
    the difference between a fixture that renders what happens to be in the
    database and one that renders what you meant to look at — and it is the
    failure that hid 23 real layout defects in sm64_tracker for a week, because
    every sweep was measuring empty-state placeholders.

    `setup` runs in the page before measuring; it may click, seed, or inject.
    `at` is a CSS selector for the element the story is ABOUT, so probes and
    screenshots can be scoped to it rather than re-selecting and picking wrong.

    **`setup` MUST BE IDEMPOTENT.** It runs once per viewport, not once per
    sweep, so a bare `.click()` on anything that TOGGLES puts the component
    into a different state at every size — open, closed, open. That is not a
    declared state, it is sampled data wearing a Story's name, and it is the
    exact failure this class exists to prevent.

    It also fails in the most convincing way available: the closing frame gets
    measured mid-transition, so the probe reports real elements at real
    coordinates hundreds of pixels outside the viewport. It reads as a
    responsive layout defect, at one viewport only, which is precisely what a
    genuine breakpoint bug looks like (game-learnings, 2026-07-28 — three
    "defects" ~340px past the edge, all of them a settings panel sliding shut).

    Write the guard, not the gesture::

        setup="if (!document.querySelector('.panel-open')) gear.click()"
    """
    name: str
    at: str
    setup: str = ""            # JavaScript evaluated in the page before measuring
    skip_if: str = ""          # JavaScript; truthy means "not applicable here"


@dataclass(frozen=True)
class Project:
    """How to reach one project's UI, and what its rules are.

    serve
        Context manager yielding a base URL.  The project owns booting its own
        app — uilab never guesses how.

    page_path
        Path appended to the base URL to reach the page under test.

    stylesheet
        File containing the CSS whose breakpoints drive the viewport matrix.
        uilab derives probe points on BOTH sides of every declared threshold,
        because a threshold is the only place a layout can newly break.

    shell_selectors
        Class-name prefixes that a VIEWPORT media query is allowed to style.
        Everything else is component-internal and belongs in a container query.
        Empty means "do not enforce the rule".

    never_truncate
        Selectors carrying irreducible information — a defect if they ellipsise.

    may_clip
        Selectors whose whole purpose is to hide their own content: a collapsed
        panel, a clamped preview. Without these, adding one collapse control
        turns every folded card into a reported clipping defect.

    may_bleed
        Selectors whose ::before/::after is MEANT to paint across other boxes —
        a modal scrim, a focus ring drawn outside its control, a full-bleed
        hero wash. Everything else must keep its decoration inside its own box
        and its ancestors' padding; see probe class 5.

    ready_selector
        A selector that exists only once the app has actually rendered. The
        sweep waits for it before measuring anything. Without one, a page that
        paints a shell or a loading state first gets measured in that state and
        reported clean.

    stories
        The state catalogue.  Empty is legal; the sweep then measures whatever
        the app happens to show, which is where most projects start and most
        blind spots live.

    extra_viewports
        Sizes worth probing regardless of what the stylesheet declares — a user
        report, a device you actually own, the WCAG reflow floor.

    include_default_viewports
        Whether to probe uilab's own default points — the WCAG 1.4.10 reflow
        floor at 320px, a desktop size and a short window. True is right for
        anything meant to be responsive. Set it False for a FIXED-GEOMETRY
        surface: a recording rig, a kiosk, an embedded panel. game-learnings'
        column grid raises "viewport too narrow" below its minimum BY DESIGN,
        so probing 320px there ships a guaranteed failure — and the only other
        way to land that is a permanent `known_defects` row, which is a lie
        about what is broken and exactly what `stale_exemptions` exists to
        prevent. Declared thresholds are still derived either way.

        This does not license switching the defaults off because a sweep is
        noisy. WCAG reflow is an objective floor for anything a person
        resizes; this is for surfaces where the probe is not merely failing
        but meaningless.

    legacy_transition_rules
        Existing violations of the one-transition law, grandfathered so the law
        can land on a codebase without a cleanup task attached to it.
    """
    serve: Callable[[], contextlib.AbstractContextManager[str]]
    page_path: str = "/"
    stylesheet: Path | Sequence[Path] | None = None
    ready_selector: str = ""
    shell_selectors: Sequence[str] = ()
    never_truncate: Sequence[str] = ()
    may_clip: Sequence[str] = ()
    may_bleed: Sequence[str] = ()
    stories: Sequence[Story] = ()
    extra_viewports: Sequence[tuple[int, int]] = ()
    include_default_viewports: bool = True
    known_defects: dict[str, str] = field(default_factory=dict)
    legacy_viewport_rules: Sequence[str] = ()
    legacy_transition_rules: Sequence[str] = ()

    @contextlib.contextmanager
    def open(self) -> Iterator[str]:
        """Yield the full URL of the page under test."""
        with self.serve() as base:
            yield base.rstrip("/") + "/" + self.page_path.lstrip("/")


def stylesheet_paths(project: Project) -> list[Path]:
    """The project's stylesheets, however it declared them.

    One file or several: a workbench's chrome is routinely split across a
    layout sheet, a component sheet and a theme sheet, and a matrix derived
    from only the first is a matrix with holes in it.
    """
    declared = project.stylesheet
    if declared is None:
        return []
    if isinstance(declared, Path):
        return [declared]
    return list(declared)

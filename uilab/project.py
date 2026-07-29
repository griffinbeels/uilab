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
    """
    serve: Callable[[], contextlib.AbstractContextManager[str]]
    page_path: str = "/"
    stylesheet: Path | None = None
    ready_selector: str = ""
    shell_selectors: Sequence[str] = ()
    never_truncate: Sequence[str] = ()
    stories: Sequence[Story] = ()
    extra_viewports: Sequence[tuple[int, int]] = ()
    known_defects: dict[str, str] = field(default_factory=dict)

    @contextlib.contextmanager
    def open(self) -> Iterator[str]:
        """Yield the full URL of the page under test."""
        with self.serve() as base:
            yield base.rstrip("/") + "/" + self.page_path.lstrip("/")

"""The driver seam — and the reason it exists.

Browser automation is the fastest-moving dependency this module has. Playwright
is today's answer; it replaced Puppeteer as the default, which replaced
Selenium, and something will replace it. WebDriver BiDi is already standardising
much of what CDP does today. When that happens the cost of switching should be
ONE file here, not a rewrite of every probe, sweep and gate that sits on top.

So two things, not one:

  1. A narrow `Driver` protocol. Everything above it — probes, sweep, cascade
     helper, story runner — speaks only this, and none of them import
     playwright. Grep for the import: it appears in exactly one module.

  2. A CONFORMANCE SUITE (tests/test_driver_conformance.py) that every
     registered driver runs. An interface alone is a promise; the suite is what
     makes "swap it in" a checkable claim rather than an aspiration. A new
     driver is trusted when it goes green, and until then it is a candidate.

Pick with UILAB_DRIVER, or `use_driver()` in-process. Registration is one
decorator, so adding a candidate never edits this file's logic.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class Page(Protocol):
    """One open page. Deliberately small: five verbs and two queries.

    Anything a probe needs that is NOT here is a sign the protocol is wrong,
    not a reason to reach around it — reaching around is how a driver becomes
    unswappable one convenience at a time.
    """

    def goto(self, url: str) -> None: ...

    def set_viewport(self, width: int, height: int) -> None: ...

    def evaluate(self, expression: str) -> object:
        """Run JS in the page and return a JSON-serialisable value."""

    def screenshot(self, clip: dict | None = None) -> bytes:
        """PNG bytes of the viewport, or of `clip` when given.

        `clip` is `{"x", "y", "width", "height"}` in CSS pixels, and the image
        comes back scaled by the device pixel ratio — so a caller cropping a
        fixed grid gets real pixels rather than an upscale of a smaller
        capture.
        """

    def click(self, selector: str) -> None:
        """Click the ONE element matching `selector`.

        Must raise if the selector matches more than one element. Silently
        acting on the first match is the single most expensive failure mode
        this module exists to prevent — it produced three separate wrong-answer
        debugging sessions before uilab was extracted.
        """

    def count(self, selector: str) -> int: ...

    def wait_for(self, selector: str, timeout_ms: int = 10_000) -> None:
        """Block until at least one element matches and is visible.

        The alternative every consumer reaches for is `sleep(n)`, and it is
        wrong in both directions: too short and you measure a loading state,
        too long and every viewport in a sweep pays for it. Measuring a
        loading state is the worse half -- an app that renders its shell
        first reports a page with none of its content on it, and the sweep
        calls that clean.
        """

    def wait_ms(self, milliseconds: int) -> None:
        """Wait, really.

        The obvious `evaluate("new Promise(r => setTimeout(r, 400))")` does not
        work through a wrapper that turns a statement into a function BODY: the
        promise is constructed, never returned, so nothing awaits it and the
        call returns immediately. It reads as a wait and is a no-op, which is
        worse than no wait at all -- a probe then samples a layout mid-render
        and reports whatever it caught (measured 2026-07-28: four browser tests
        with four 400ms waits finished in 1.57s).
        """

    def problems(self) -> list[str]:
        """Every fault the page reported since the last call, then forget them.

        Console errors, uncaught exceptions, responses with status >= 400 and
        failed requests — one human-readable line each.

        DRAINING is the contract, not an optimisation. Callers ask once per
        rung, per viewport, per sweep cell; a list that accumulated would
        report rung 2's exception again under rung 7's name, which is worse
        than silence because it sends the reader to the wrong file.

        Why this is on a protocol meant to stay narrow: a sweep that measures
        a throwing page and reports it clean is not a weaker gate, it is a
        FALSE one — the report is indistinguishable from a page that works.
        Every consumer wrote this listener by hand before it lived here.
        """

    def matched_styles(self, selector: str, prop: str) -> list[dict]:
        """Every CSS rule that matches `selector` and sets `prop`, in cascade
        order, as `{selector, value, important, condition, origin}`.

        ASK THE ENGINE. A hand-rolled walk over `document.styleSheets` looks
        easy and is not: with CSS Nesting every CSSStyleRule carries an (empty,
        truthy) `cssRules` list, so the obvious `if (rule.cssRules) recurse`
        skips every real rule and reports a clean sheet. That exact bug cost
        hours. Chrome answers this properly via CDP `CSS.getMatchedStylesForNode`.
        """

    def emulate_motion(self, reduced: bool) -> None:
        """Force `prefers-reduced-motion`.

        Raw headless Chrome defaults to `reduce`, and any stylesheet that
        honours it then makes every transition finish instantly — so animation
        checks report defects that exist only in the harness. Drivers MUST
        default to no-preference; this is for testing the reduced case on
        purpose.
        """


@runtime_checkable
class Driver(Protocol):
    name: str

    def launch(self, headless: bool = True,
               viewport: tuple[int, int] | None = None,
               device_scale_factor: float = 1.0,
               use_system_browser: bool = False) -> Iterator[Page]:
        """Context manager yielding a Page. Must clean up on exception.

        `use_system_browser` asks for the browser the human actually has
        installed rather than the one this library bundles. It is not a
        preference: a tool that photographs a page in order to judge how a
        RECORDING will look must drive the same binary the recording does, and
        a bundled build is a different renderer with different font
        rasterisation — so the shot quietly stops answering the question it
        was taken to answer. A driver that cannot honour it may ignore it.
        """


_REGISTRY: dict[str, Callable[[], Driver]] = {}


def register(name: str) -> Callable[[Callable[[], Driver]], Callable[[], Driver]]:
    """Register a driver factory under `name`.

    A candidate driver adds itself with this and appears in the conformance
    suite automatically — no edit to the selection logic below, which is what
    keeps "try a new tool" cheap.
    """
    def wrap(factory: Callable[[], Driver]) -> Callable[[], Driver]:
        _REGISTRY[name] = factory
        return factory
    return wrap


def available() -> list[str]:
    """Registered driver names, for the conformance suite to parametrise over."""
    _load_builtins()
    return sorted(_REGISTRY)


_DEFAULT = "playwright"
_selected: str | None = None


def use_driver(name: str) -> None:
    """Select a driver for this process (tests, or trying a candidate)."""
    global _selected
    _load_builtins()
    if name not in _REGISTRY:
        raise LookupError(f"unknown driver {name!r}; registered: {sorted(_REGISTRY)}")
    _selected = name


def get_driver(name: str | None = None) -> Driver:
    """The driver to use: explicit argument, then UILAB_DRIVER, then default."""
    _load_builtins()
    chosen = name or _selected or os.environ.get("UILAB_DRIVER") or _DEFAULT
    if chosen not in _REGISTRY:
        raise LookupError(
            f"unknown driver {chosen!r}; registered: {sorted(_REGISTRY)}. "
            "Set UILAB_DRIVER to one of those, or register a new one with "
            "@uilab.driver.register.")
    return _REGISTRY[chosen]()


def _load_builtins() -> None:
    if _REGISTRY:
        return
    from uilab.drivers import playwright_driver  # noqa: F401  (self-registers)

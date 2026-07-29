"""The Playwright driver — the ONLY module in uilab that imports playwright.

If that stops being true, the swap-a-better-tool property is gone. Grep for
`import playwright` before merging anything.

Why Playwright is the current default, in one paragraph each:

  strict locators — `page.locator(sel)` refuses to act when the selector
  matches more than one element, raising immediately rather than silently
  taking the first. Three separate debugging sessions were lost to
  `querySelector` returning an empty-state card instead of the populated one
  that had the defect.

  reduced_motion defaults to "no-preference" — raw headless Chrome defaults to
  "reduce", so any stylesheet honouring it makes every transition snap and an
  animation check reports a harness artefact as a defect.

  CDP is still reachable — `context.new_cdp_session(page)` gives the raw
  protocol where it is genuinely better, which is how matched_styles() asks the
  style engine directly instead of re-implementing the cascade.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator

from playwright.sync_api import sync_playwright

from uilab.driver import register


class PlaywrightPage:
    def __init__(self, page, cdp) -> None:
        self._page = page
        self._cdp = cdp
        self._faults: list[str] = []
        # Registered at construction, not per call. Attaching when someone
        # thinks to ask would miss everything that happened before — which is
        # most of what a page load does wrong.
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)

    def _on_console(self, message) -> None:
        if message.type == "error":
            self._faults.append(f"console.error: {message.text}")

    def _on_page_error(self, error) -> None:
        self._faults.append(f"pageerror: {error}")

    def _on_response(self, response) -> None:
        if response.status >= 400:
            self._faults.append(f"HTTP {response.status} {response.url}")

    def _on_request_failed(self, request) -> None:
        self._faults.append(f"requestfailed: {request.url} ({request.failure})")

    def problems(self) -> list[str]:
        drained, self._faults = self._faults, []
        return drained

    def goto(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded")

    def set_viewport(self, width: int, height: int) -> None:
        self._page.set_viewport_size({"width": width, "height": height})

    def evaluate(self, expression: str) -> object:
        # Wrapped so a bare expression and a statement block both work, matching
        # what CDP's Runtime.evaluate accepts — otherwise every probe has to
        # remember which form Playwright wants.
        return self._page.evaluate(f"() => {{ return ({expression}); }}"
                                   if expression.strip().startswith("(")
                                   else f"() => {{ {expression} }}")

    def screenshot(self, clip: dict | None = None) -> bytes:
        return self._page.screenshot(clip=clip) if clip else self._page.screenshot()

    def click(self, selector: str) -> None:
        # .click() on a Locator is strict by construction: it raises on a
        # multi-match instead of guessing. That refusal is the point.
        self._page.locator(selector).click()

    def count(self, selector: str) -> int:
        return self._page.locator(selector).count()

    def wait_for(self, selector: str, timeout_ms: int = 10_000) -> None:
        self._page.locator(selector).first.wait_for(
            state="visible", timeout=timeout_ms)

    def emulate_motion(self, reduced: bool) -> None:
        self._page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")

    def wait_ms(self, milliseconds: int) -> None:
        self._page.wait_for_timeout(milliseconds)

    def matched_styles(self, selector: str, prop: str) -> list[dict]:
        """Cascade-ordered rules setting `prop` on the element, from the engine."""
        self._cdp.send("DOM.enable")
        self._cdp.send("CSS.enable")
        root = self._cdp.send("DOM.getDocument")["root"]["nodeId"]
        node = self._cdp.send("DOM.querySelector",
                              {"nodeId": root, "selector": selector})["nodeId"]
        if not node:
            raise LookupError(f"no element matches {selector!r}")
        got = self._cdp.send("CSS.getMatchedStylesForNode", {"nodeId": node})

        out: list[dict] = []
        inline = got.get("inlineStyle")
        if inline:
            for entry in inline.get("cssProperties", []):
                if entry.get("name") == prop and not entry.get("disabled"):
                    out.append({"selector": "<inline style>", "value": entry.get("value"),
                                "important": bool(entry.get("important")),
                                "condition": "", "origin": "inline"})
        # matchedCSSRules arrives LEAST-specific first; keep that order so a
        # reader can see who wins by reading down.
        for match in got.get("matchedCSSRules", []):
            rule = match.get("rule", {})
            text = ", ".join(s.get("text", "")
                             for s in rule.get("selectorList", {}).get("selectors", []))
            condition = " & ".join(
                media.get("text", "")
                for media in (rule.get("media") or []) if media.get("text"))
            for entry in rule.get("style", {}).get("cssProperties", []):
                # `range` marks a declaration the AUTHOR actually wrote. CDP
                # also reports implicit longhand expansions with no range, and
                # counting those lists every rule twice.
                if entry.get("range") is None:
                    continue
                if entry.get("name") == prop and not entry.get("disabled"):
                    out.append({"selector": text, "value": entry.get("value"),
                                "important": bool(entry.get("important")),
                                "condition": condition,
                                "origin": rule.get("origin", "regular")})
        return out


class _PlaywrightDriver:
    name = "playwright"

    def __init__(self) -> None:
        self._play = None
        self._open_contexts = 0

    @contextlib.contextmanager
    def _playwright(self):
        """One Playwright instance per driver, reference-counted.

        `sync_playwright()` CANNOT BE NESTED on a thread — a second one raises
        "It looks like you are using Playwright Sync API inside the asyncio
        loop. Please use the Async API instead", which names the wrong cause
        and sends you looking for asyncio you never wrote.

        That is not merely a test problem. Holding a live window open and a
        fresh browser beside it is a real thing to want: comparing what the
        human is looking at against a clean-room load is the first move in
        half of all "is this my state or the page?" questions. A driver that
        can only have one browser at a time cannot answer it.
        """
        if self._open_contexts == 0:
            self._play = sync_playwright().start()
        self._open_contexts += 1
        try:
            yield self._play
        finally:
            self._open_contexts -= 1
            if self._open_contexts == 0:
                finished, self._play = self._play, None
                with contextlib.suppress(Exception):
                    finished.stop()

    @contextlib.contextmanager
    def launch(self, headless: bool = True,
               viewport: tuple[int, int] | None = None,
               device_scale_factor: float = 1.0,
               use_system_browser: bool = False) -> Iterator[PlaywrightPage]:
        width, height = viewport or (1440, 900)
        with self._playwright() as play:
            browser = play.chromium.launch(
                headless=headless,
                # `channel` picks the installed Chrome over the bundled
                # Chromium. Passed conditionally rather than as channel=None,
                # which is an explicit request for the bundled build.
                **({"channel": "chrome"} if use_system_browser else {}))
            # reduced_motion is named explicitly rather than left to the
            # default. The default is already correct; saying it out loud is
            # what stops a future edit from quietly inheriting the headless
            # `reduce` that cost this project an afternoon.
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=device_scale_factor,
                reduced_motion="no-preference",
                color_scheme="dark")
            page = context.new_page()
            cdp = context.new_cdp_session(page)
            try:
                yield PlaywrightPage(page, cdp)
            finally:
                with contextlib.suppress(Exception):
                    context.close()
                with contextlib.suppress(Exception):
                    browser.close()


    @contextlib.contextmanager
    def attach(self, endpoint: str,
               match_url: str | None = None) -> Iterator[PlaywrightPage]:
        with self._playwright() as play:
            browser = play.chromium.connect_over_cdp(endpoint)
            try:
                open_pages = [page for context in browser.contexts
                              for page in context.pages]
                chosen = next((page for page in open_pages
                               if match_url is None or match_url in page.url),
                              None)
                if chosen is None:
                    raise LookupError(
                        f"no open page at {endpoint} matches {match_url!r}; "
                        f"open pages: {[page.url for page in open_pages]}")
                # Deliberately NOT bring_to_front(). This runs while the human
                # is typing, and a window that raises itself mid-sentence eats
                # the keystrokes and leaves them editing the wrong thing.
                yield PlaywrightPage(chosen, chosen.context.new_cdp_session(chosen))
            finally:
                # Closes the CONNECTION, not the browser: connect_over_cdp
                # attaches to a process this library did not start and must
                # not end. The window stays exactly as the human left it.
                with contextlib.suppress(Exception):
                    browser.close()

    @contextlib.contextmanager
    def launch_with_debugging(self, port: int) -> Iterator[PlaywrightPage]:
        """A browser with a CDP port open — the conformance suite's stand-in
        for "a window the human already had".

        Not part of the Driver protocol: production callers attach to a browser
        someone else started, and a driver that cannot open a debugging port is
        still a conformant driver.
        """
        with self._playwright() as play:
            browser = play.chromium.launch(
                headless=True, args=[f"--remote-debugging-port={port}"])
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                reduced_motion="no-preference", color_scheme="dark")
            page = context.new_page()
            try:
                yield PlaywrightPage(page, context.new_cdp_session(page))
            finally:
                with contextlib.suppress(Exception):
                    browser.close()


@register("playwright")
def _factory() -> _PlaywrightDriver:
    return _PlaywrightDriver()


__all__ = ["PlaywrightPage"]

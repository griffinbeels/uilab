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

    def screenshot(self) -> bytes:
        return self._page.screenshot()

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

    @contextlib.contextmanager
    def launch(self, headless: bool = True) -> Iterator[PlaywrightPage]:
        with sync_playwright() as play:
            browser = play.chromium.launch(headless=headless)
            # reduced_motion is named explicitly rather than left to the
            # default. The default is already correct; saying it out loud is
            # what stops a future edit from quietly inheriting the headless
            # `reduce` that cost this project an afternoon.
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                device_scale_factor=1,
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


@register("playwright")
def _factory() -> _PlaywrightDriver:
    return _PlaywrightDriver()


__all__ = ["PlaywrightPage"]

"""EVERY registered driver runs this. Green here is what "swappable" means.

An interface is a promise. This suite is the check. When something better than
Playwright arrives — WebDriver BiDi, whatever follows it — the work is a new
module under uilab/drivers/ that registers itself, and then this file. If it
goes green the rest of uilab cannot tell the difference, because nothing above
the seam imports a browser library.

Each test names the REAL failure it guards, because every one of them was paid
for once already.
"""
import contextlib
import http.server
import socket
import threading
from pathlib import Path

import pytest

from uilab.driver import available, get_driver

PAGE = """<!doctype html><html><head><style>
  body { margin: 0; overflow-x: hidden; }
  .card { height: 200px; overflow: hidden; border: 1px solid #000; }
  .card { height: 120px; }                     /* later rule wins */
  @media (max-width: 500px) { .card { height: 80px; } }
  .twin { color: red; }
  .grid { display: grid; }
  .grid > .stretched { height: 40px; }
  .motion { transition: opacity 300ms linear; opacity: 1; }
  @media (prefers-reduced-motion: reduce) { .motion { transition-duration: 1ms; } }
</style></head><body>
  <div class="card" id="card"><p style="height:400px">tall</p></div>
  <div class="twin">one</div><div class="twin">two</div>
  <div class="grid"><div class="tall" style="height:300px"></div>
                    <div class="stretched" id="stretched"></div></div>
  <div class="motion" id="motion"></div>
</body></html>"""


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    root = tmp_path_factory.mktemp("page")
    (root / "index.html").write_text(PAGE, encoding="utf-8")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def log_message(self, *a):
            pass

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        server.shutdown()


@pytest.fixture(params=available())
def page(request, url):
    with get_driver(request.param).launch() as opened:
        opened.goto(url)
        yield opened


def test_evaluate_returns_values(page):
    assert page.evaluate("(1 + 1)") == 2
    assert page.evaluate("(document.querySelectorAll('.twin').length)") == 2


def test_viewport_override_is_exact(page):
    page.set_viewport(900, 1180)
    assert page.evaluate("(window.innerWidth)") == 900
    assert page.evaluate("(window.innerHeight)") == 1180


def test_click_REFUSES_an_ambiguous_selector(page):
    """The one that cost three debugging sessions.

    `.twin` matches two elements. A driver that quietly acts on the first is
    worse than one that fails, because the failure is silent and the wrong
    element's measurements look perfectly plausible.
    """
    with pytest.raises(Exception):
        page.click(".twin")


def test_reduced_motion_defaults_to_no_preference(page):
    """Headless browsers commonly default to `reduce`, and any stylesheet that
    honours it then makes every transition finish instantly — so an animation
    check reports a defect that exists only in the harness."""
    assert page.evaluate(
        "(matchMedia('(prefers-reduced-motion: reduce)').matches)") is False


def test_reduced_motion_can_still_be_forced(page):
    page.emulate_motion(True)
    assert page.evaluate(
        "(matchMedia('(prefers-reduced-motion: reduce)').matches)") is True
    page.emulate_motion(False)


def test_matched_styles_reports_the_cascade_in_order(page):
    """Must come from the STYLE ENGINE. A hand-rolled walk over
    document.styleSheets misses everything under CSS Nesting, because a plain
    CSSStyleRule then carries an empty-but-truthy `cssRules` list."""
    page.set_viewport(1200, 800)
    rules = page.matched_styles("#card", "height")
    values = [rule["value"] for rule in rules]
    assert "200px" in values and "120px" in values, values
    assert values.index("200px") < values.index("120px"), (
        "rules must arrive least-specific-first so the winner reads last")


def test_matched_styles_carries_the_media_condition(page):
    page.set_viewport(400, 800)
    rules = page.matched_styles("#card", "height")
    assert any("80px" == r["value"] and "500px" in r["condition"] for r in rules), rules


def test_screenshot_returns_png_bytes(page):
    data = page.screenshot()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_count_matches_the_dom(page):
    assert page.count(".twin") == 2
    assert page.count(".nothing-here") == 0


def test_every_registered_driver_is_covered():
    """A registry with one entry is fine; an EMPTY one means this whole file
    silently tested nothing."""
    assert available(), "no drivers registered — the suite proved nothing"


def test_wait_for_returns_once_the_element_is_visible(page):
    """The alternative is sleep(n), which measures a loading state when it is
    too short and taxes every viewport in a sweep when it is too long."""
    page.wait_for(".card", timeout_ms=5000)
    assert page.count(".card") == 1


def test_wait_for_raises_rather_than_returning_quietly(page):
    """A wait that gives up silently is worse than no wait: the caller then
    measures whatever happened to be on screen and believes it."""
    with pytest.raises(Exception):
        page.wait_for(".never-appears", timeout_ms=300)


def test_wait_ms_actually_waits(page):
    """A wait that returns immediately is worse than no wait: a probe then
    samples mid-render and reports whatever it caught. Four browser tests with
    four 400ms waits once finished in 1.57s, because the wait was written as an
    un-awaited promise inside a function body."""
    import time
    started = time.monotonic()
    page.wait_ms(350)
    elapsed = (time.monotonic() - started) * 1000
    assert elapsed >= 300, f"wait_ms(350) returned after {elapsed:.0f}ms"

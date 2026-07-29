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

# A page that misbehaves in all four ways problems() must notice. Kept separate
# from PAGE so every other test in this file keeps measuring a clean document.
NOISY_PAGE = """<!doctype html><html><body>
  <img src="/definitely-not-here.png" alt="">
  <script>
    console.error("a console error");
    setTimeout(() => { throw new Error("an uncaught page error"); }, 0);
  </script>
</body></html>"""


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    root = tmp_path_factory.mktemp("page")
    (root / "index.html").write_text(PAGE, encoding="utf-8")
    (root / "noisy.html").write_text(NOISY_PAGE, encoding="utf-8")

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


def test_problems_is_empty_on_a_clean_page(page):
    """The half that makes the other half meaningful: a probe that always
    reports something is a probe nobody reads."""
    page.wait_for("body")
    assert page.problems() == []


def test_problems_reports_console_pageerror_and_failed_requests(page, url):
    """A sweep that measures a throwing page and calls it clean is worse than
    no sweep: the report is indistinguishable from a page that works."""
    page.goto(url.replace("index.html", "noisy.html"))
    # NOT wait_for("img"): a broken image has no box, so it is never "visible"
    # and the wait can only time out. The document is what has arrived.
    page.wait_for("body")
    page.wait_ms(300)          # the pageerror is thrown from a timeout callback
    found = " || ".join(page.problems())
    assert "a console error" in found, found
    assert "an uncaught page error" in found, found
    assert "definitely-not-here.png" in found, found


def test_problems_drains_so_the_same_fault_is_not_reported_twice(page, url):
    """Callers ask per rung, per viewport, per sweep cell. A list that
    accumulated would blame rung 7 for rung 2's exception."""
    page.goto(url.replace("index.html", "noisy.html"))
    page.wait_for("body")
    page.wait_ms(300)
    assert page.problems() != []
    assert page.problems() == []


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height straight out of the IHDR chunk.

    Parsed by hand rather than with Pillow: the conformance suite must be able
    to judge a driver's screenshot without dragging an image library into the
    seam it is testing.
    """
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))


@pytest.mark.parametrize("driver_name", available())
def test_launch_honours_viewport_and_pixel_density(driver_name, url):
    """A shot of a recording rig is worthless at the wrong pixel density: the
    column crops to a 1080x1920 short, and a devicePixelRatio the harness
    picked instead of the machine's records a blurry upscale."""
    with get_driver(driver_name).launch(
            viewport=(1200, 800), device_scale_factor=2.0) as opened:
        opened.goto(url)
        assert opened.evaluate("(window.innerWidth)") == 1200
        assert opened.evaluate("(window.devicePixelRatio)") == 2
        assert png_size(opened.screenshot()) == (2400, 1600)


@pytest.mark.parametrize("driver_name", available())
def test_screenshot_clip_crops_to_the_rect_in_css_pixels(driver_name, url):
    """The clip is given in CSS px and comes back scaled by the device pixel
    ratio — that is what makes a column crop land on real pixels rather than
    on an upscale of a smaller capture."""
    with get_driver(driver_name).launch(
            viewport=(1200, 800), device_scale_factor=2.0) as opened:
        opened.goto(url)
        clipped = opened.screenshot(
            clip={"x": 10, "y": 20, "width": 300, "height": 400})
        assert png_size(clipped) == (600, 800)


@pytest.mark.parametrize("driver_name", available())
def test_launch_defaults_are_unchanged(driver_name, url):
    """The defaults are load-bearing: every existing caller passes nothing."""
    with get_driver(driver_name).launch() as opened:
        opened.goto(url)
        assert opened.evaluate("(window.innerWidth)") == 1440
        assert opened.evaluate("(window.devicePixelRatio)") == 1


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.parametrize("driver_name", available())
def test_attach_is_implemented_or_refuses_by_name(driver_name):
    """`attach` is the one verb a future driver may genuinely be unable to
    provide — WebDriver BiDi makes no promise about connecting to a browser
    someone else started. So the contract is: do it, or say
    NotImplementedError. What is NOT conformant is a signature that refuses
    the arguments, or a silent success against an endpoint with nothing
    behind it.

    Port 9 is the discard protocol; nothing listens there.
    """
    driver = get_driver(driver_name)
    # Checked FIRST, and it is the half that makes this test able to fail at
    # all: without it a driver with no `attach` raises AttributeError, which
    # is an Exception, and the assertion below waves it through. Caught by
    # writing the test before the implementation and watching it go green.
    assert hasattr(driver, "attach"), (
        f"{driver_name} has no `attach`. Implement it, or define it raising "
        f"NotImplementedError — silence is not one of the two answers.")
    with pytest.raises(Exception) as caught:
        with driver.attach("http://127.0.0.1:9", match_url=None):
            pass
    assert not isinstance(caught.value, (TypeError, AttributeError)), (
        f"{driver_name}.attach(endpoint, match_url=...) has the wrong "
        f"signature: {caught.value}")


@pytest.mark.parametrize("driver_name", available())
def test_attach_reaches_a_page_someone_else_opened(driver_name, url):
    """The whole point: the state belongs to the browser that was already
    running. A driver that launched its own would answer a different question
    with no error — which is exactly how a screenshot of a clean-room
    reproduction gets mistaken for a screenshot of the reported bug."""
    driver = get_driver(driver_name)
    debug_port = free_port()
    with driver.launch_with_debugging(debug_port) as owner:
        owner.goto(url)
        owner.evaluate("window.__marker = 'set by the owner';")
        try:
            with driver.attach(f"http://127.0.0.1:{debug_port}",
                               match_url="index.html") as attached:
                assert attached.evaluate("(window.__marker)") == "set by the owner"
        except NotImplementedError:
            pytest.skip(f"{driver_name} does not implement attach")


@pytest.mark.parametrize("driver_name", available())
def test_attach_does_not_navigate(driver_name, url):
    """Scroll position, flipped toggles and a half-typed input are the reason
    to attach at all. A goto() on the way in throws away the very thing being
    looked at, and the resulting screenshot looks perfectly plausible."""
    driver = get_driver(driver_name)
    debug_port = free_port()
    with driver.launch_with_debugging(debug_port) as owner:
        owner.goto(url)
        owner.evaluate("document.title = 'mutated in place';")
        with driver.attach(f"http://127.0.0.1:{debug_port}",
                           match_url="index.html") as attached:
            assert attached.evaluate("(document.title)") == "mutated in place"


@pytest.mark.parametrize("driver_name", available())
def test_attach_raises_when_no_page_matches(driver_name, url):
    """A silent fallback to 'some other tab' is how you photograph the wrong
    window and believe it."""
    driver = get_driver(driver_name)
    debug_port = free_port()
    with driver.launch_with_debugging(debug_port) as owner:
        owner.goto(url)
        with pytest.raises(LookupError):
            with driver.attach(f"http://127.0.0.1:{debug_port}",
                               match_url="no-such-page"):
                pass

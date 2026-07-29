"""describe() turns "this looks wrong" into numbers.

It sits beside explain(): explain answers WHY a property has its value,
describe answers WHAT the element actually is right now — including the two
questions a style panel cannot answer, namely whether the element is really
the thing under the cursor and whether its own box is cutting it off.
"""
import http.server
import socket
import threading

import pytest

from uilab.driver import available, get_driver
from uilab.inspect import describe

PAGE = """<!doctype html><html><head><style>
  body { margin: 0; font: 16px/1.5 monospace; }
  .card { position: absolute; left: 40px; top: 60px; width: 200px; height: 50px;
          overflow: hidden; color: rgb(10, 20, 30); background: rgb(200, 200, 200); }
  .tall { height: 400px; }
  .cover { position: absolute; left: 0; top: 0; width: 400px; height: 400px;
           background: rgb(0, 0, 0); opacity: 0.5; }
</style></head><body>
  <div class="card" id="card"><div class="tall">overflowing content</div></div>
  <div class="cover" id="cover"></div>
</body></html>"""


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    root = tmp_path_factory.mktemp("inspect")
    (root / "index.html").write_text(PAGE, encoding="utf-8")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, *args):
            pass

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        server.shutdown()


@pytest.fixture(params=available())
def page(request, url):
    with get_driver(request.param).launch() as opened:
        opened.goto(url)
        yield opened


def test_describe_reports_the_box_in_css_pixels(page):
    assert describe(page, "#card")["box"] == {
        "x": 40, "y": 60, "width": 200, "height": 50}


def test_describe_names_what_is_actually_on_top(page):
    """The question a style panel cannot answer. An element can be perfectly
    styled, correctly positioned and completely unreachable, and every
    property you inspect will look right."""
    found = describe(page, "#card")["topmost_at_centre"]
    assert "cover" in found, found


def test_describe_reports_a_box_that_is_clipping_its_own_content(page):
    """The silent one: both end states look correct in a screenshot, and only
    the measurement shows the bottom of the card is being cut off."""
    assert describe(page, "#card")["clipped_by_own_box"] is True
    assert describe(page, "#cover")["clipped_by_own_box"] is False


def test_describe_raises_on_a_selector_that_matches_nothing(page):
    with pytest.raises(LookupError):
        describe(page, ".not-here")

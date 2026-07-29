"""explain() against the real bug it was built for.

A card would not collapse. The rule matched, had the highest specificity, came
last, `var()` resolved — and the used height was unchanged. An inline
`!important` was ignored too. Hours went into it because every tool in reach
reported the CASCADE and stopped there.

This file has now falsified TWO of its author's explanations of that bug. The
first fixture asserted grid stretch was the cause — a grid item with a definite
height is not stretched, per spec. The second asserted the automatic minimum
size floored it — that does not floor a grid item's own used height in Chrome
either. Both were written as fact and neither survived a test.

That is the argument for the tool, not against it: `explain()` reports used
alongside declared, so "these agree" would have redirected the search on the
first round instead of the fifth. The original bug's true cause is still open.

Contract, both halves:
  - report the matched rules in cascade order, from the style engine;
  - when the winner and the USED value disagree, name the mechanism AND the
    remedy, because at that point the cascade is not the explanation.
"""
import http.server
import socket
import threading

import pytest

from uilab.cascade import explain
from uilab.driver import available, get_driver

# `#floored` asks for 50% of an auto-height parent. A percentage against an
# indefinite containing block is not resolvable, so the used value is the
# content height instead — declared and used disagree, which is the case
# explain() exists for.
#
# Two earlier attempts at this fixture were WRONG and the tests said so: a grid
# item with a definite height is not stretched, and the automatic minimum size
# does not floor a grid item's own used height in Chrome. Both were my
# explanations of the original bug; both were falsified here before they could
# be written into the tool as fact.
PAGE = """<!doctype html><html><head><style>
  body { margin: 0; }
  .auto-parent { }
  .box { height: 80%; }
  .box { height: 50%; }
  .plain { height: 40px; }
</style></head><body>
  <div class="auto-parent"><div class="box" id="floored"><i style="display:block;height:300px"></i></div></div>
  <div class="plain" id="plain"></div>
</body></html>"""


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    root = tmp_path_factory.mktemp("cascade")
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


def test_reports_the_cascade_winner_when_nothing_is_odd(page):
    result = explain(page, "#plain", "height")
    assert result.declared == "40px"
    assert result.used == "40px"
    assert not result.layout_note, "nothing is overriding this one"


def test_rules_arrive_least_specific_first_and_are_not_duplicated(page):
    """Reading down the list must show who wins, last — and each authored
    declaration appears ONCE. CDP also reports implicit longhand expansions,
    and counting those listed every rule twice."""
    result = explain(page, "#floored", "height")
    assert [r["value"] for r in result.rules] == ["80%", "50%"]


def test_names_the_disagreement_the_cascade_cannot_explain(page):
    """The whole point: the cascade says 50%, the box is 300px, and a reader
    shown only the matched rules concludes the browser is broken."""
    result = explain(page, "#floored", "height")
    assert result.declared == "50%", "the cascade winner is still reported"
    assert result.used == "300px", "the percentage did not resolve"
    assert result.layout_note, "the disagreement must be explained, not hidden"
    assert "percentage" in result.layout_note, (
        "the note must name a mechanism worth checking, not just say 'differs'")


def test_stays_quiet_when_the_cascade_IS_the_explanation(page):
    """The other half of being useful: a note on every property would be noise
    and would train a reader to ignore it."""
    assert not explain(page, "#plain", "height").layout_note


def test_str_is_readable_at_a_glance(page):
    text = str(explain(page, "#floored", "height"))
    assert "used value:" in text and "winning rule:" in text
    assert "300px" in text and "50%" in text

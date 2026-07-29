"""Probe class 5: decorations painting onto a box they do not own.

Classes 1-4 all walk the DOM, and a ::before is not in the DOM. That blind spot
shipped two real bugs in one project, each reported by the user three times
while every sweep called the page clean (sm64_tracker, 2026-07-28 and -29): a
rank banner's wash bled sideways across a grid gap onto the neighbouring
column, and then bled vertically onto the banner stacked beneath it, covering
its lower edge so the two colours met with no seam.

The page below reproduces that geometry exactly — the same -8px/-12px bleeds
across the same too-small gap — so the regression this file guards is the
shipped one, not a sketch of it.
"""
import http.server
import json
import socket
import threading

import pytest

from uilab.driver import available, get_driver
from uilab.sweep import PROBE_JS

PAGE = """<!doctype html><html><head><style>
  body { margin: 0; background: #06101d; color: #fff; font: 13px sans-serif; }
  .card { padding: 16px; width: 420px; background: #0d1a2b; margin-bottom: 40px; }
  .stack { display: flex; flex-direction: column; gap: 5px; }
  .band { position: relative; min-height: 30px; }
  /* The shipped bleeds: fine side by side, pointed at each other stacked. */
  .band::before {
    content: ""; position: absolute; z-index: -1;
    top: -8px; bottom: -12px; left: -16px; right: 0;
    background-image: linear-gradient(90deg, #2f6d3f, transparent 88%);
  }
  /* Same box, same geometry, no paint — must not be reported. */
  .ghost::before { background-image: none; background-color: transparent; }
  .sealed::before { top: 0; bottom: 0; }
  .sealed:first-child::before { top: -8px; }
  .sealed:last-child::before { bottom: -12px; }
  /* inset:0, not a strip: a fixed strip at the top of the viewport does not
     reach a band 500px down the page, and the exemption it is meant to prove
     then goes untested while every assertion stays green (caught by mutating
     this one rule on its own, 2026-07-29). */
  .floaty { position: fixed; inset: 0; background: #000; }
</style></head><body>

  <!-- FIRST in the document, so it is inside the viewport whatever the
       driver's default size is. A fixed overlay is SUPPOSED to be over the
       page — that is what it is for. -->
  <section class="card" id="overlaid"><div class="stack">
    <div class="band" id="under"><b>under</b></div>
    <div class="floaty">nav</div>
  </div></section>

  <!-- One band, alone in its card: the left bleed lands in the card's own
       padding, which is what a bleed is FOR. -->
  <section class="card" id="lone"><div class="stack">
    <div class="band" id="only"><b>only</b></div>
  </div></section>

  <!-- The bug. 20px of bleed across a 5px gap. -->
  <section class="card" id="collide"><div class="stack">
    <div class="band" id="upper"><b>upper</b></div>
    <div class="band" id="lower">
      <b>lower</b><span>delta</span><i style="display:block;height:4px;
        background:#888"></i>
    </div>
  </div></section>

  <!-- The fix: inner edges keep to themselves, outer edges still bleed. -->
  <section class="card" id="fixed"><div class="stack">
    <div class="band sealed" id="sup"><b>upper</b></div>
    <div class="band sealed" id="slow"><b>lower</b><span>delta</span></div>
  </div></section>

  <!-- Same geometry, nothing painted. -->
  <section class="card" id="ghosted"><div class="stack">
    <div class="band ghost" id="gup"><b>upper</b></div>
    <div class="band ghost" id="glow"><b>lower</b></div>
  </div></section>
</body></html>"""


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    root = tmp_path_factory.mktemp("decoration")
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
        opened.evaluate(PROBE_JS)
        yield opened


def decorations(page, at, **config):
    config = {"at": at, "neverTruncate": [], "mayClip": [], "mayBleed": [], **config}
    return page.evaluate(f"(__uilab({json.dumps(config)}))")["decoration"]


def test_a_bleed_into_its_ancestors_padding_is_not_a_defect(page):
    """The whole reason to write a negative offset. If this fires, the probe is
    unusable — nearly every wash in a real app bleeds into its card."""
    assert decorations(page, "#lone") == []


def test_a_decoration_covering_a_sibling_is_reported(page):
    found = decorations(page, "#collide")
    assert found, "the shipped rank-banner geometry must be caught"
    assert any("#upper::before over #lower" == item["selector"] for item in found), \
        f"expected the upper band's wash over the lower band, got {found}"


def test_the_collision_is_reported_once_not_once_per_inky_descendant(page):
    """The real defect hit ELEVEN descendants — five hat layers, the name, the
    delta, the progress track and its fill. Eleven rows for one bug is a list
    nobody reads, and the box actually covered is the outermost one."""
    found = decorations(page, "#collide")
    over_lower = [item for item in found if item["selector"].endswith("over #lower")]
    assert len(over_lower) == 1, f"one report per collided subtree, got {found}"


def test_sealing_the_inner_edges_clears_it(page):
    """The fix that shipped: inner edges flat, outer edges still bleeding."""
    assert decorations(page, "#fixed") == []


def test_a_decoration_that_paints_nothing_is_not_a_defect(page):
    """Identical geometry, no ink. A transparent pseudo overlapping something is
    invisible, and reporting it would bury the ones that are not."""
    assert decorations(page, "#ghosted") == []


def test_a_fixed_overlay_is_allowed_to_be_over_things(page):
    """A sticky header or bottom nav floats over content by design — that is
    what it is for, and at some scroll offset it is over everything."""
    assert decorations(page, "#overlaid") == []


def test_may_bleed_exempts_a_declared_host(page):
    """Scrims, focus rings and full-bleed hero washes cross other boxes on
    purpose. The project declares them; the probe does not guess."""
    assert decorations(page, "#collide", mayBleed=["#upper"]) == []


def test_the_guard_can_actually_fail(page):
    """Every test above asserts an EMPTY list, and an empty list is what a
    broken probe returns too. This is the one that proves the instrument works
    — without it the whole file is green forever."""
    assert decorations(page, "#collide"), \
        "the probe reports nothing even on the geometry it was written for"

"""Frame traces: the diagnoses, and the recorder that feeds them.

Most of this file needs no browser, on purpose — the questions a trace answers
are arithmetic over samples, and arithmetic is where the bugs it caught
actually lived. Each case names the real failure it guards; every one of them
was found by hand, one round trip at a time, before this module existed.

The last tests are the design bet: the recorder runs IN the page at rAF rate,
and it keeps running while the driver is busy triggering and screenshotting. If
either stops holding, a trace silently becomes a coarse poll and every "did it
start from rest" answer becomes noise — so both are measured rather than
assumed. (The bet is NOT that `evaluate` cannot await a Promise; it can, and
saying otherwise here was this file's own first bug. trace.py has the reason.)
"""
import http.server
import socket
import threading

import pytest

from uilab.driver import available, get_driver
from uilab.trace import Track, Trace, record

PAGE = """<!doctype html><html><head><style>
  body { margin: 0; background: #0b1520; }
  #box {
    width: 40px; height: 40px; background: #6997cc;
    transform: translateX(0px);
    transition: transform 400ms linear;
  }
  #box.go { transform: translateX(300px); }
</style></head><body>
  <div id="box"></div>
  <button id="run" onclick="document.getElementById('box').classList.add('go')">go</button>
</body></html>"""


def track(name="t", **series):
    """A Track from {field: [values]}, one frame per value at 16ms apart."""
    length = len(next(iter(series.values())))
    frames = [{"t": i * 16.0, **{k: v[i] for k, v in series.items()}}
              for i in range(length)]
    return Track(name=name, frames=frames)


# ---- the diagnoses ------------------------------------------------------

def test_a_curve_that_leaps_on_the_first_frame_is_not_at_rest():
    """`cubic-bezier(.2,.9,.2,1)` was 35% travelled by 16ms and read as a hop
    rather than a launch — reported from four screenshots one frame apart,
    with both end states looking perfect."""
    hop = track(x=[0, 35, 60, 80, 92, 100])
    ok, fraction = hop.starts_at_rest("x")
    assert not ok and fraction == pytest.approx(0.35)

    launch = track(x=[0, 1, 8, 30, 70, 100])
    ok, fraction = launch.starts_at_rest("x")
    assert ok and fraction == pytest.approx(0.01)


def test_landing_on_the_right_value_is_not_coming_to_rest():
    """A wing flap on sin(2*pi*p) returns to exactly the right rotation having
    never slowed down. The value trace is perfect; only differencing frames
    tells the two apart."""
    stops_dead = track(a=[0, 25, 50, 75, 100])
    ok, deltas = stops_dead.comes_to_rest("a")
    assert not ok and deltas == [25, 25, 25]

    eases = track(a=[0, 60, 85, 96, 100, 100])
    ok, _ = eases.comes_to_rest("a")
    assert ok


def test_a_bar_that_gives_progress_back_is_caught():
    """"you gave me progress and then took it away!!!!" — a progress bar may
    never overshoot, and it must ease DOWN when the new value is lower."""
    assert track(w=[0, 20, 60, 100]).monotone("w")
    assert track(w=[79, 61, 40, 18]).monotone("w"), "a downward swap is fine"
    assert not track(w=[0, 60, 110, 100]).monotone("w"), "overshoot is not"


def test_two_strings_visible_at_once_is_a_rendering_fault():
    """A simultaneous crossfade puts BOTH at 0.5 across the middle of its run.
    Stacked in one grid cell that does not read as a blend."""
    out = track("out", opacity=[1.0, 0.75, 0.5, 0.25, 0.0])
    incoming = track("in", opacity=[0.0, 0.25, 0.5, 0.75, 1.0])
    assert out.overlaps(incoming), "a crossfade overlaps"

    seq_out = track("out", opacity=[1.0, 0.5, 0.0, 0.0, 0.0])
    seq_in = track("in", opacity=[0.0, 0.0, 0.0, 0.5, 1.0])
    assert seq_out.overlaps(seq_in) == [], "an exchange does not"


def test_same_timing_is_a_measurement_not_an_intention():
    """"This should all happen with the same timing." Four things on four
    clocks read as several things happening near each other."""
    together = Trace(tracks={
        "icon": track("icon", v=[0, 1, 2, 3, 3]),
        "text": track("text", v=[0, 1, 2, 3, 3]),
    })
    ok, settled = together.together(["icon", "text"], "v")
    assert ok, settled

    apart = Trace(tracks={
        "icon": track("icon", v=[0, 3, 3, 3, 3]),
        "text": track("text", v=[0, 1, 2, 3, 3]),
    })
    ok, settled = apart.together(["icon", "text"], "v")
    assert not ok and settled == {"icon": 16.0, "text": 48.0}


def test_a_missing_element_records_a_frame_rather_than_raising():
    """An element that does not exist YET is a real state, and usually the
    interesting one — an overlay that has not mounted, a card mid-swap."""
    partial = Track(name="x", frames=[{"t": 0.0}, {"t": 16.0, "opacity": 1.0}])
    assert partial.values("opacity") == [1.0]
    assert partial.starts_at_rest("opacity")[0]


# ---- the recorder -------------------------------------------------------

@pytest.fixture(scope="module")
def url(tmp_path_factory):
    root = tmp_path_factory.mktemp("trace-page")
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


def test_the_recorder_samples_at_frame_rate_not_at_round_trip_rate(page):
    """Half the design bet. Polling from here samples every few tens of ms,
    which cannot answer "what happened in the first frame" — the question that
    found the hop. A 400ms transition must yield far more samples than a poll
    could."""
    result = record(page, watch={"box": "#box"},
                    trigger=lambda p: p.click("#run"), ms=500)
    box = result.of("box")
    assert len(box.frames) > 15, (
        f"only {len(box.frames)} frames in 500ms -- the in-page recorder is "
        "not running; a trace has silently become a coarse poll")
    assert box.travel("x") > 250, box.values("x")


def test_recording_continues_while_the_driver_is_busy(page):
    """The OTHER half, and the actual reason the recorder is in the page.

    An awaited rAF walker samples at frame rate too -- `evaluate` does await a
    Promise, measured -- but it holds the driver for the whole window, so the
    trigger and the screenshots cannot happen inside it. Then the numbers and
    the strip describe two different runs, which is worse than having neither.
    Three screenshots are three round trips. This is the test that earns the
    word "correlated": measured 2026-07-29 the strip lands at 0/250/500ms with
    15 frames recorded between each pair and a largest inter-frame gap of
    17.8ms -- one frame. A blocking recorder cannot produce that; its shots all
    collapse to the end of the window.
    """
    window_ms = 500
    result = record(page, watch={"box": "#box"},
                    trigger=lambda p: p.click("#run"), ms=window_ms, shots=3)
    box = result.of("box")
    assert len(result.shots) == 3
    at = [int(label.removesuffix("ms")) for label, _ in result.shots]

    # The strip must SPAN the window. A first shot taken near its end is the
    # signature of shooting after the fact, and the shape the numbers-and-strip
    # split exists to rule out.
    assert at[0] <= window_ms * 0.2, f"strip starts at {at[0]}ms, not the start"
    assert at[-1] >= window_ms * 0.6, f"strip ends at {at[-1]}ms, too early"

    # And recording must not pause for any of them. Measured max gap is one
    # frame; a driver round trip that stalled the recorder would leave a hole
    # far larger than this, which is what makes it a real check rather than a
    # restatement of "frames exist".
    times = [frame["t"] for frame in box.frames]
    widest = max(b - a for a, b in zip(times, times[1:]))
    assert widest < 50, (
        f"a {widest:.0f}ms hole in the frames -- recording stalls while the "
        "driver is busy, so the strip and its numbers describe different runs")
    for lo, hi in zip(at, at[1:]):
        between = sum(1 for t in times if lo < t < hi)
        assert between >= 5, f"only {between} frames between {lo}ms and {hi}ms"
    assert box.travel("x") > 250, box.values("x")


def test_a_linear_transition_reports_itself_as_linear(page):
    """The instrument, checked against a curve whose answer is known: linear
    does NOT start at rest, and does NOT come to rest. If a trace called this
    eased, nothing it said about a real curve would mean anything."""
    result = record(page, watch={"box": "#box"},
                    trigger=lambda p: p.click("#run"), ms=800)
    box = result.of("box")
    # Prove the motion HAPPENED before judging its shape. A trace of nothing
    # moving reports "at rest" trivially, so without this the test passes for
    # the one reason that makes it worthless -- the same trap as an instrument
    # that can only return the answer you expect.
    assert box.travel("x") > 250, f"nothing moved: {box.values('x')[:5]}"
    assert box.monotone("x")
    assert not box.comes_to_rest("x", tail=3)[0], (
        f"linear must stop dead, got deltas {box.comes_to_rest('x', tail=3)[1]}")


def test_screenshots_come_back_labelled_and_correlated(page):
    """The manual strip, automated -- numbers for WHEN, shots for whether it
    looks like the thing you meant."""
    result = record(page, watch={"box": "#box"},
                    trigger=lambda p: p.click("#run"), ms=400, shots=3)
    assert len(result.shots) == 3
    assert all(data and label.endswith("ms") for label, data in result.shots)

"""Frame traces: what moved, every frame, after you touched something.

    "if I click on a button and it animates, would it be able to reproduce the
    type of debugging strategy that I employed where I provided you consecutive
    screenshots like that? ... For any UI interaction, being able to
    autonomously debug those would be cool"  (2026-07-29)

That debugging strategy worked, and it was entirely manual: the human watched
an animation, caught it mid-flight, and sent frames one apart. Every finding it
produced was a number nobody could see by watching — a card at 35% of its
travel on the first frame reading as a hop, a wing arriving at the right angle
having never slowed down, a bar landing full when the header showed 40%, two
strings both at 0.5 opacity in one grid cell. Each cost a round trip through a
person.

This module is that strategy without the person. It records at the page's own
frame rate and answers the questions those rounds actually asked, because raw
frames are a log and a log is not a diagnosis:

    trace.starts_at_rest()   a displacement curve whose first frame is already
                             a third of the way there reads as a jump, and the
                             end states look perfect either way
    trace.comes_to_rest()    ending at the right VALUE and coming to REST are
                             different properties; only differencing frames
                             tells them apart
    trace.monotone()         a bar that eases backwards, or overshoots and
                             returns, is progress being taken away
    a.overlaps(b)            two things visible at once that should exchange
    trace.together()         "this should all happen with the same timing" as a
                             number rather than an intention

WHY THE RECORDER LIVES IN THE PAGE — the reason is CONCURRENCY, not capability.
An awaited requestAnimationFrame walker does work: measured 2026-07-29,
`evaluate("new Promise(...)")` returns 42, and a rAF walker returns its 8
frames. This file claimed the opposite in three places first, which is the
instrument telling a story about itself instead of measuring — the same fault
it exists to catch.

What an awaited walker cannot do is let anything else happen while it runs. It
holds the driver for the whole window, and `record()` must fire the trigger and
take screenshots DURING that window; a blocking call makes both impossible, so
you could have frames or you could have a strip, never the two correlated. The
second reason is contractual: promise-awaiting is Playwright's behaviour, not
the Driver protocol's — raw CDP `Runtime.evaluate` hands back a promise HANDLE
unless asked for `awaitPromise`, so a trace built on it would quietly stop
working when the tool is swapped, which is the one property uilab exists to
keep. Recording in the page and reading the array once afterwards needs nothing
of the seam but that it returns a value.

SCREENSHOTS ARE COARSER THAN THE NUMBERS, deliberately. Each one is a
round-trip, so a handful across an animation is realistic and one per frame is
not. That is the right split anyway: the numbers say WHEN and HOW MUCH, the
strip says whether it looks like the thing you meant. `film()` returns them as
one labelled row via sheet.compose, the same shape the width sheets use.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

TRACE_JS = (Path(__file__).parent / "trace.js").read_text(encoding="utf-8")

# Frames closer together than this are the same moment for "did these land
# together" purposes -- one 60Hz frame, rounded up.
FRAME_MS = 17.0

# How much of its speed a motion must shed each frame at the end to count as
# coming to REST rather than stopping dead. Noise-immune by construction: a
# linear curve's final partial frame differs from its neighbours by hundredths
# of a pixel, which any strict `<` comparison reads as deceleration.
DECELERATION = 0.8


@dataclass
class Track:
    """One watched element's samples across the trace."""

    name: str
    frames: list[dict]          # [{t, ...sample}] with the sample flattened in

    def values(self, field_name: str) -> list:
        return [f[field_name] for f in self.frames if f.get(field_name) is not None]

    def times(self, field_name: str) -> list[float]:
        return [f["t"] for f in self.frames if f.get(field_name) is not None]

    def travel(self, field_name: str) -> float:
        """How far this field moved in total, first sample to last."""
        seen = self.values(field_name)
        return abs(seen[-1] - seen[0]) if len(seen) >= 2 else 0.0

    def starts_at_rest(self, field_name: str, *, within_ms: float = FRAME_MS,
                       max_fraction: float = 0.05) -> tuple[bool, float]:
        """(ok, fraction travelled by `within_ms`).

        A curve is judged by watching from its MIDDLE, which is why an ease
        that is already a third of the way there on the first frame survives
        review and still reads as a hop rather than a launch.
        """
        seen = [(f["t"], f[field_name]) for f in self.frames
                if f.get(field_name) is not None]
        if len(seen) < 2:
            return True, 0.0
        total = abs(seen[-1][1] - seen[0][1])
        if total == 0:
            return True, 0.0
        early = [v for t, v in seen if t <= within_ms]
        moved = abs(early[-1] - seen[0][1]) if early else 0.0
        fraction = moved / total
        return fraction <= max_fraction, fraction

    def comes_to_rest(self, field_name: str, *, tail: int = 3) -> tuple[bool, list[float]]:
        """(ok, the last `tail` per-frame deltas).

        Ending on the right value and coming to rest are different properties,
        and a value trace looks perfect for both -- so difference consecutive
        frames. Anything still moving on its final frame reads as stopping
        dead, unless another motion takes over on the very next one.
        """
        seen = self.values(field_name)
        # Trim the frames after it stopped. A recording longer than the motion
        # otherwise ends in a run of identical samples, and EVERY curve then
        # reports itself as easing -- including a linear one, which is the
        # sharpest possible false negative for this question.
        while len(seen) >= 2 and abs(seen[-1] - seen[-2]) <= 1e-9:
            seen.pop()
        if len(seen) < tail + 1:
            return True, []
        deltas = [abs(b - a) for a, b in zip(seen[-tail - 1:], seen[-tail:])]
        # Each step must be MEANINGFULLY smaller than the last, not merely
        # smaller. A bare `b < a` calls a linear transition eased: the final
        # frame is a partial one, so its delta lands a hundredth of a pixel
        # under its neighbours and floating point does the rest -- measured as
        # [12.525, 12.5249, 12.493] on a 400ms linear translate, which passed
        # "strictly decreasing" 1 run in 4 and made this test flaky.
        #
        # A fraction rather than an absolute floor, because "how small is still
        # moving" depends on the unit and this is asked of pixels, opacity and
        # percentages alike. Real easing sheds far more than a fifth per frame
        # at the end; linear sheds nothing.
        return all(b <= a * DECELERATION for a, b in zip(deltas, deltas[1:])), deltas

    def monotone(self, field_name: str, *, tolerance: float = 0.001) -> bool:
        """True when the field only ever moves one way (either way)."""
        seen = self.values(field_name)
        if len(seen) < 2:
            return True
        deltas = [b - a for a, b in zip(seen, seen[1:])]
        return (all(d >= -tolerance for d in deltas)
                or all(d <= tolerance for d in deltas))

    def settled_at(self, field_name: str, *, tolerance: float = 0.01) -> float | None:
        """When this field last CHANGED -- i.e. when it finished moving."""
        rows = [(f["t"], f[field_name]) for f in self.frames
                if f.get(field_name) is not None]
        last = None
        for (_, a), (t, b) in zip(rows, rows[1:]):
            if abs(b - a) > tolerance:
                last = t
        return last

    def overlaps(self, other: "Track", *, field_name: str = "opacity",
                 floor: float = 0.0) -> list[float]:
        """Times where BOTH tracks are visible -- for things that should
        exchange rather than cross-fade. Two different strings stacked at 0.5
        do not read as a blend; they read as a rendering fault."""
        mine = {f["t"]: f.get(field_name) for f in self.frames}
        return [t for f in other.frames
                for t in [f["t"]]
                if (f.get(field_name) or 0) > floor and (mine.get(t) or 0) > floor]


@dataclass
class Trace:
    tracks: dict[str, Track]
    shots: list[tuple[str, bytes]] = field(default_factory=list)

    def of(self, name: str) -> Track:
        if name not in self.tracks:
            raise KeyError(f"nothing watched under {name!r}; "
                           f"watched: {sorted(self.tracks)}")
        return self.tracks[name]

    def together(self, names, field_name: str, *,
                 within_ms: float = FRAME_MS) -> tuple[bool, dict]:
        """(ok, {name: settled-at}) -- "the same timing" as a measurement.

        Four things animating on four clocks read as several things happening
        near each other rather than one gesture, and the difference is a number
        nobody can see by watching.
        """
        settled = {n: self.of(n).settled_at(field_name) for n in names}
        known = [v for v in settled.values() if v is not None]
        if len(known) < 2:
            return True, settled
        return (max(known) - min(known)) <= within_ms, settled

    def film(self, **kwargs) -> bytes:
        """The shots as one labelled row -- the manual strip, automated."""
        from uilab import sheet
        return sheet.compose(self.shots, **kwargs)


def record(page, *, watch: dict[str, str], trigger=None, ms: float = 1500,
           properties=(), shots: int = 0, settle_ms: float = 0) -> Trace:
    """Install the recorder, fire `trigger`, and hand back the frames.

    `watch` is {name: css selector}. `trigger` is called with the page once
    recording has begun -- a click, an evaluate, anything; None just records.
    `properties` names extra computed properties to capture per frame (custom
    properties included, e.g. "--climb-color"). `shots` evenly spaced
    screenshots are taken during the window and correlated by label.

    A selector that matches nothing records None for that frame rather than
    raising: an element that does not exist YET is a real state, and it is
    usually the interesting one.
    """
    page.evaluate(TRACE_JS)
    # The recorder's own cap is generous: the WINDOW is measured here, from
    # when the trigger RETURNS. A trigger has unpredictable latency of its own
    # -- Playwright's click runs actionability checks first -- and charging
    # that to the window made the trace intermittently miss the motion
    # entirely, which then reports "at rest" for a curve that never moved.
    # Recording starts BEFORE the trigger so no first frame is lost, and the
    # cap only exists so a caller who never reads cannot leave a loop running.
    page.evaluate("__uilabTraceStart(" + json.dumps({
        "watch": watch, "properties": list(properties),
        "ms": ms * 4 + 5000}) + ")")
    if settle_ms:
        time.sleep(settle_ms / 1000)
    if trigger is not None:
        trigger(page)

    captured: list[tuple[str, bytes]] = []
    started = time.monotonic()
    if shots > 0:
        for index in range(shots):
            target = started + (ms / 1000) * (index / max(1, shots - 1))
            remaining = target - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            captured.append((f"{int((time.monotonic() - started) * 1000)}ms",
                             page.screenshot()))
    remaining = (ms / 1000) - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)

    raw = page.evaluate("JSON.stringify(__uilabTraceRead())")
    frames = json.loads(raw)["frames"] if isinstance(raw, str) else (raw or {}).get("frames", [])

    tracks: dict[str, Track] = {}
    for name in watch:
        rows = []
        for frame in frames:
            sample = frame.get(name)
            rows.append({"t": frame["t"], **(sample or {})})
        tracks[name] = Track(name=name, frames=rows)
    return Trace(tracks=tracks, shots=captured)

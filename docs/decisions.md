# Instrumentation decisions

The point of this file: **research the tooling once, here.** When a project on
this machine needs UI instrumentation it consumes `uilab`; when something better
than the current tool appears, it gets evaluated here, once, and every project
inherits the outcome.

Each entry says what was chosen, what it was chosen OVER, and — most usefully —
the concrete failure that decided it. A decision without the failure behind it
gets re-litigated by the next person to have an opinion.

---

## 2026-07-28 — Widening the Page/Driver protocol for a recording rig

**Chosen:** four additions — `Page.problems()`, `Page.screenshot(clip)`,
`Driver.launch(viewport, device_scale_factor, use_system_browser)` and
`Driver.attach(endpoint, match_url)`.

**Over:** leaving game-learnings' Node + playwright-core tools in place and
consuming uilab only for the sweep.

**Deciding failures:**

| Failure | What fixes it |
|---|---|
| `sweep.run()` measures a page with an uncaught exception on it and reports zero defects — indistinguishable from a page that works | `problems()`, drained per call so rung 2's exception is never reported under rung 7's name |
| A shot at the harness's own pixel density records a blurry upscale of the frame that will actually be recorded | `viewport` + `device_scale_factor` at launch |
| Bundled Chromium is a different renderer from installed Chrome, so a shot taken to judge a recording stops answering that question, silently | `use_system_browser` |
| A fresh browser has none of the human's scroll position, flipped toggles or selection, so "look at what I'm seeing" quietly becomes a clean-room reproduction | `attach`, which never navigates |

**Cost accepted:** the protocol grew from "five verbs and two queries" to seven
and two. `describe()` was deliberately kept OFF the protocol — it is JS through
`evaluate`, like `probes.js` — to hold the line the docstring draws.

**Conformance rule for `attach`:** implement it, or raise
`NotImplementedError`. WebDriver BiDi makes no promise about connecting to a
browser someone else started, and nothing above the seam assumes it exists.

**Two things this cost, recorded because both misdirect:**

- `sync_playwright()` **cannot be nested on a thread.** The second one raises
  *"Please use the Async API instead"*, which names asyncio the caller never
  wrote. The driver now holds one reference-counted instance — and that is a
  capability, not a workaround: holding a live window open beside a fresh load
  is the first move in half of all "is this my state or the page?" questions,
  and the old shape could not do it at all.
- The `attach` contract test **passed before `attach` existed**, because
  `AttributeError` is an `Exception` and "raises something" waved a missing
  method through. It asserts `hasattr` first now. Only caught by watching a
  new test go green against no implementation — which is the argument for
  running the red step rather than assuming it.

---

## 2026-07-28 — Default viewports are a default, not a law

**Chosen:** `Project.include_default_viewports`, defaulting True.

**Deciding failure:** game-learnings is a fixed-geometry recording rig whose
column grid RAISES *"viewport too narrow"* below its minimum, by design.
`DEFAULT_POINTS` includes the WCAG 1.4.10 reflow floor at 320px, so its first
sweep would have shipped a guaranteed failure. The only ways to land that are a
permanent `known_defects` row — a lie about what is broken, and precisely what
`stale_exemptions` exists to prevent — or a flag.

**What this does NOT license:** switching the defaults off because a sweep is
noisy. WCAG reflow is an objective floor for anything a person resizes. This is
for surfaces with a FIXED geometry, where the probe is not merely failing but
meaningless. Declared thresholds are still derived either way, so the flag can
never quietly turn a sweep back into hand-picked widths.

---

## 2026-07-28 — Laws get a module, not just a plugin function

**Chosen:** `uilab/laws.py` as a named registry. The container-query law moves
in and the transition-replacement law joins it; `pytest_plugin` re-exports both
so no consumer's import breaks.

**Why:** the point of this module is that a rule learned once is enforced
everywhere. A set of such rules with no name and no home does not get added
to — the container-query law sat alone inside a pytest plugin for its whole
life. The second law arrived from a consumer that had been hand-maintaining it
in three separate CSS comments with nothing checking it.

**The second law:** CSS `transition` is not additive across rules. A state
block (`:hover`, `.open`) declaring its own `transition` shorthand WHOLESALE
REPLACES the base rule's, so the property loses its transition while the state
is active and regains it on exit — smooth one way, a snap the other, under CSS
that reads as identical. Shorthand only: `transition-delay` refines rather than
replaces, and a law with false positives gets switched off.

**Rule for adding one:** every law states in its own docstring what it
structurally CANNOT catch. A guard whose blind spots are undocumented gets
trusted past its range, which is worse than no guard — it converts "we did not
check" into "we checked".

---

## 2026-07-28 — Playwright over raw CDP

**Chosen:** Playwright (Chromium), with a raw CDP session underneath for the
style engine.

**Over:** hand-written CDP-over-websocket (what this replaced), Puppeteer,
Selenium/WebDriver.

**Deciding failures**, all from one week of sm64_tracker work on raw CDP:

| Failure | Cost | What fixes it |
|---|---|---|
| `querySelector` returned an empty-state card instead of the populated one carrying the defect | 3 separate wrong-answer sessions | **Strict locators.** Playwright refuses to act when a selector matches more than one element. The documented rationale is the exact failure: silently acting on the first match is worse than a clear error. |
| Every animation measured as an instant snap | A whole feature declared broken that was fine | **`reduced_motion` defaults to `no-preference`.** Raw headless Chrome defaults to `reduce`; any stylesheet honouring it then finishes every transition in 0.01ms. |
| A hand-rolled cascade walker examined 0 of 1164 rules | Hours | **`CSS.getMatchedStylesForNode`.** With CSS Nesting a plain `CSSStyleRule` carries an empty-but-truthy `cssRules`, so `if (rule.cssRules) recurse` skips everything. Never re-implement the cascade. |

**Not chosen, and why:**

- *Puppeteer* — Chrome-only, and its assertion/locator ergonomics are what
  Playwright was built to improve on.
- *Selenium / WebDriver* — the standards-track option, and WebDriver BiDi is
  closing the gap on CDP-only capabilities. Worth re-evaluating when BiDi
  exposes matched styles; today it does not.
- *Cypress* — in-browser runner, awkward for a Python-driven pytest gate.

**Cost accepted:** one dependency plus a ~110 MB browser download per machine.

**What would change this:** a driver that exposes matched styles and the box
model through a standard (BiDi), or a tool with better agent ergonomics. The
swap is one module under `uilab/drivers/` plus a green run of
`tests/test_driver_conformance.py` — nothing above the seam imports a browser
library, deliberately.

---

## 2026-07-28 — Semantic assertions over screenshot diffing

**Chosen:** measure the page (overflow, clipping, truncation, overlap) and
assert on the measurements.

**Over:** pixel-diff visual regression (Percy, Chromatic, Applitools,
`toHaveScreenshot`).

**Why:** the apps here have live clocks, recording timers and animation. The
visual-regression literature is largely about *managing flake* — masking dynamic
regions, tuning pixel tolerance, suppressing animation. Every one of those is a
maintenance tax paid per baseline. Semantic assertions need no baseline, survive
dynamic content, and each result names the defect instead of reporting that 37
pixels differ.

**Where screenshots still earn their place:** a contact sheet for a human eye.
It is a review aid, never a gate. Assertions cannot see "correct but ugly".

---

## 2026-07-28 — Declared component states (Story) over sampled data

**Chosen:** a project declares the states worth measuring.

**Over:** pointing the harness at whatever the database currently holds.

**Deciding failure:** sm64_tracker's fixture booted the real app against a
snapshot of the dev database. With nobody playing, that database had no active
target — so every sweep for a week rendered *empty-state placeholders* and
reported the page clean. Seeding one target surfaced **23 real layout defects**
at the same 36 viewports. A feature built in that week rendered zero times, with
no error, because the fixture never mounted the component it lived on.

The name and shape are borrowed from Component Story Format: a story *declares*
the state rather than hoping the data produces it, and the same declaration
feeds sweeps, screenshots and unit tests. Storybook itself is not used — it
needs a bundler, and these are zero-build importmap apps.

---

## 2026-07-29 — Probe the paint, not only the tree (decoration collisions)

**Chosen:** derive a `::before`/`::after`'s painted rect from its host's padding
box and report it when it covers a box that is neither the host nor inside it.

**Over:** the previous position, written into probes.js as a comment on the
overlap probe — *"decorative washes overlap by design"* — which skipped them.

**Deciding failure:** every probe here walks the DOM, and a pseudo-element is
not in the DOM. sm64_tracker's rank banners paint their colour wash in a
`::before`. It bled `-16px` sideways across a 12px grid gap onto the next
column, and `-8px/-12px` vertically onto the banner stacked beneath it — 15.2px
of overlap, so the second wash covered the first one's lower edge and the two
colours met with no seam. The user reported it three times over two days
(*"it's overlapping in all scenarios"*, *"there needs to be some vertical
margin between the bottom of the green rect and the top of the white rect"*)
while three consecutive sweeps reported the page clean, because the only thing
wrong was in paint. Adding the class found both bugs on the first run, plus the
sideways one at widths where it was invisible: the gradient had already faded
to `transparent 88%` by the 4px that crossed.

The law is not "a decoration may not leave its host" — bleeding into an
ancestor's own padding or grid gap is the normal reason to write one. It is
that a decoration may not cover a box belonging to something else. Four rules
keep it usable, each mutation-proved separately in
`tests/test_probes_decoration.py`: skip pseudos that paint no ink, skip fixed
and sticky targets (floating over content is what they are for), report once
per collided *subtree* rather than once per inky descendant (the real defect hit
eleven), and honour a project's `may_bleed` for scrims and focus rings.

**Limit, stated because it will matter:** only *absolutely positioned* pseudos
have derivable geometry, and only when the host is itself positioned. A static
`::before` pushed out of its host by a negative margin is still invisible here.

---

## 2026-07-29 — A supported-width floor, but only one the product enforces

**Chosen:** `Project.min_viewport_width` drops narrower widths from the matrix,
and `sweep.dropped_viewports()` names every one it dropped.

**Over:** measuring every width the stylesheet mentions, forever.

**Deciding input:** *"We don't HAVE to support super super super small width
window sizes. I think going forward, the minimum officially supported width we
should support is 850px."* sm64_tracker is a desktop app beside an emulator, not
a public site; 21 of its 36 probe widths were below 850px, and more than half
its owed defects lived only there (97 → 43 rows).

**The condition that makes it honest:** the floor must be one the shipped app
ENFORCES, or it does not narrow the supported range, it hides defects inside it.
In that consumer the same constant drives the desktop window's `min_size`, its
default geometry *and* a clamp on restored geometry — `min_size` constrains
dragging but not the size a window is created at, and neither touches a
geometry file written before the rule existed. A test fails if the sweep's floor
and the window's floor ever disagree.

**Priced, not buried:** a floor above 320px retires the WCAG 1.4.10 reflow
probe, and any mobile-shell CSS below it stops being measured while still
shipping. `dropped_viewports()` exists so that shows up on every run instead of
being rediscovered later.

---

## 2026-07-29 — Contact sheets as an implementation tool, not a final check

**Chosen:** `uilab.sheet` — one surface, every width, one image, no baseline.

**Deciding input:** *"for most features while you're implementing, you could
probably solve a lot of your bugs by simply taking screenshots and going 'oh...
there's only one rank standard' while you're thinking, or 'oh, UI elements are
intersecting, weird...'"*

Both examples are drawn from real failures in this module's own consumer, and
both survived every assertion. A fixture seeded a star with one strategy, so the
card drew ONE rank banner instead of two and an entire class of defect was
unmeasurable for weeks. Two banner washes overlapped by 15px at every stacked
width while four DOM probes reported the page clean. Each is unmistakable in a
single shot, and neither is expressible as a defect: the first is the fixture
being wrong, the second is paint.

The 2026-07-27 entry above already concluded that screenshots earn their place
as "a contact sheet for a human eye". This is that, built — and the correction
to it is the *timing*: a review aid used after the work is worth far less than
the same image looked at while the work is still being written.

---

## Open questions

- **Playwright's trace viewer** records DOM snapshots per action and would
  likely have shortened several of the failures above. Not yet wired in.
- **Accessibility-tree assertions** are more stable than DOM structure for
  "is this reachable" checks; the unreachable-tab probe is currently DOM-based.
- **The original collapse bug is still unexplained.** Two proposed mechanisms
  (grid stretch, automatic minimum size) were both falsified by
  `tests/test_cascade_explain.py` before they could be written in as fact.

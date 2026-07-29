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

## Open questions

- **Playwright's trace viewer** records DOM snapshots per action and would
  likely have shortened several of the failures above. Not yet wired in.
- **Accessibility-tree assertions** are more stable than DOM structure for
  "is this reachable" checks; the unreachable-tab probe is currently DOM-based.
- **The original collapse bug is still unexplained.** Two proposed mechanisms
  (grid stretch, automatic minimum size) were both falsified by
  `tests/test_cascade_explain.py` before they could be written in as fact.

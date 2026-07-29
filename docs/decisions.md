# Instrumentation decisions

The point of this file: **research the tooling once, here.** When a project on
this machine needs UI instrumentation it consumes `uilab`; when something better
than the current tool appears, it gets evaluated here, once, and every project
inherits the outcome.

Each entry says what was chosen, what it was chosen OVER, and — most usefully —
the concrete failure that decided it. A decision without the failure behind it
gets re-litigated by the next person to have an opinion.

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

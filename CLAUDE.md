# uilab — development guide

Shared UI instrumentation for every project on this machine. Consumers install
it **editable**, so anything changed here is live in all of them on their next
run, with no update step and no version to pin.

That is the whole point, and it is also the whole risk. Read `consumers.json`
before changing anything under `uilab/`.

## Commands

```
uv run pytest -q                              # MUST pass; includes the driver conformance suite
uv run python -m playwright install chromium  # once per machine
uv run python tools/check_consumers.py        # run every consumer's tests against THIS tree
```

## The four rules this module exists to enforce

1. **The driver is replaceable.** Exactly one module imports a browser library
   (`uilab/drivers/playwright_driver.py`). Everything else speaks the `Page`
   protocol. Before merging anything, `grep -r "import playwright" uilab/` must
   return one file. A new driver is trusted when
   `tests/test_driver_conformance.py` goes green against it — an interface is a
   promise, the suite is the check.

2. **Ask the engine; never re-implement it.** The cascade, the box model and
   matched styles all have real APIs. A hand-rolled walk over
   `document.styleSheets` reported 0 of 1164 rules once, because CSS Nesting
   gives every `CSSStyleRule` an empty-but-truthy `cssRules` list.

3. **Semantic assertions, not screenshot diffs.** No baselines to maintain, and
   each result names the defect. Screenshots are a contact sheet for a human,
   which is a review aid and never a gate.

4. **Declared states, not sampled data.** A fixture that renders whatever the
   database holds measures the wrong page and reports it clean — that hid 23
   real defects for a week.

## Adding a consumer

One entry in `consumers.json`. Then, in the consumer:

```
uv pip install --python ".venv\Scripts\python.exe" -e <path-to-uilab> -e . pytest
```

Name `uilab` as an ordinary dependency with NO `[tool.uv.sources]` entry — see
the README for why every form of that entry is wrong here.

## When a better tool appears

Evaluate it in `docs/decisions.md`, once, with the concrete failure that decides
it. Then write the driver, run the conformance suite, and every project on this
machine gets it. Do **not** evaluate browser tooling inside a consuming project;
that is the duplication this module was extracted to end.

## Definition of done

- `uv run pytest -q` passes, conformance suite included
- `uv run python tools/check_consumers.py` is clean (or the breakage is
  deliberate and the consumer is updated in the same sitting)
- a new decision — a tool swapped, an approach rejected — has a dated entry in
  `docs/decisions.md` with the failure that decided it, not just the conclusion
- commit messages explain WHY

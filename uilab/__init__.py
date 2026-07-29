"""uilab — browser instrumentation for UI, CSS and layout work.

One shared module, installed EDITABLE into every project on this machine, so
instrumentation is researched and improved in exactly one place and every
project gets the improvement with no update step.

    from uilab import Project, Story, sweep, explain

    PROJECT = Project(serve=my_fixture_server, page_path="/ui/index.html", ...)

What it gives you:

  sweep.run(PROJECT)      every declared breakpoint, both sides, x every
                          declared component state, reporting overflow,
                          clipping, truncation and overlap
  explain(page, sel, p)   why a CSS property is what it is — matched rules
                          from the style engine, plus the layout override the
                          cascade cannot explain on its own
  Story                   a component state DECLARED rather than hoped for
  driver.use_driver(...)  swap the browser tool; a candidate is trusted once it
                          passes tests/test_driver_conformance.py

Design rules, in priority order:

  1. The driver is replaceable. Exactly one module imports playwright.
  2. Ask the engine, never re-implement it (the cascade, the box model).
  3. Semantic assertions over screenshot diffs — no baselines to maintain, and
     each result names the defect.
  4. Declared states over sampled data. A fixture that renders whatever the
     database happens to hold measures the wrong page and reports it clean.
"""
from uilab.cascade import Explanation, explain
from uilab.inspect import describe
from uilab.project import Project, Story
from uilab import driver, laws, sheet, sweep

__all__ = ["Project", "Story", "explain", "Explanation", "describe",
           "sweep", "driver", "laws", "sheet"]
__version__ = "0.1.0"

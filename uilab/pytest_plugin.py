"""Gates a consuming project gets for free.

A project points a conftest at its Project object:

    # tests/conftest.py
    from myapp.uilab_project import PROJECT
    uilab_project = PROJECT

and inherits the sweep gate, the stale-exemption gate and the container-query
law, without copying a line of test code into a third repo. That is the whole
argument for extracting this: the gates improve here, and every project gets
the improvement on its next run.
"""
from __future__ import annotations

import os

import pytest

from uilab import css, sweep

SKIP_ENV = "UILAB_SKIP"


def pytest_addoption(parser) -> None:
    parser.addoption("--uilab-driver", default=None,
                     help="browser driver to sweep with (default: playwright)")


def _project(request):
    project = getattr(request.module, "uilab_project", None)
    if project is None:
        pytest.skip("no `uilab_project` defined in this test module")
    return project


@pytest.fixture(scope="module")
def uilab_sweep(request):
    """One sweep per module — it is the expensive fixture, so share it.

    Skipping is an EXPLICIT decision (UILAB_SKIP=1), never an accident of a
    missing browser: a gate that skips itself when its dependency is absent is
    green forever, which is indistinguishable from a gate that passed.
    """
    if os.environ.get(SKIP_ENV) == "1":
        pytest.skip(f"{SKIP_ENV}=1 — layout sweep deliberately disabled")
    project = _project(request)
    return sweep.run(project, driver_name=request.config.getoption("--uilab-driver"))


def assert_no_new_defects(project, result) -> None:
    new = sweep.new_defects(project, result)
    assert not new, (
        f"{len(new)} NEW layout defect(s):\n  "
        + "\n  ".join(f"{key}\n      {detail}"
                      for key, detail in sorted(new.items())[:25]))


def assert_no_stale_exemptions(project, result) -> None:
    stale = sweep.stale_exemptions(project, result)
    assert not stale, (
        f"Fixed, but still exempted — remove {len(stale)} row(s) from "
        f"known_defects: {stale[:8]}")


def assert_components_use_container_queries(project) -> None:
    """`@media` styles the shell; component layout gates on `@container`.

    Viewport width is the wrong signal for a component whenever a shell element
    changes size at a breakpoint: the pane a card lives in is then NOT monotonic
    in window width, and no viewport threshold can express "this card is too
    narrow" — every one of them is wrong on one side of the jump.
    """
    if not project.stylesheet or not project.shell_selectors:
        pytest.skip("project declares no stylesheet or no shell selectors")
    text = css.stylesheet_text(project.stylesheet)
    shell = tuple(project.shell_selectors)
    violations = [
        f"{block.condition} :: {selector}"
        for block in css.size_blocks(css.parse_blocks(text))
        if block.kind == "media"
        for selector in block.selectors
        if not css.is_shell(selector, shell)]
    allowed = set(getattr(project, "legacy_viewport_rules", ()) or ())
    new = [v for v in violations if v not in allowed]
    assert not new, (
        "These @media rules style component-internal selectors; component "
        "layout must gate on @container against its own pane:\n  "
        + "\n  ".join(new))

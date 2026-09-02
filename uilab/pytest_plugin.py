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

from uilab import sweep
# Re-exported so no consumer's import breaks: the laws moved to uilab.laws,
# where a rule paid for once can be found and added to.
from uilab.laws import (assert_components_use_container_queries,  # noqa: F401
                        assert_one_transition_declaration)  # noqa: F401

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
    # Defensive lookup: this fixture is usable by IMPORTING it into a test
    # module, not only via the pytest11 entry point -- and that matters,
    # because an entry point only exists for an INSTALLED package. A consumer
    # whose package manager prunes the editable install (uv sync does, for
    # anything absent from the lockfile) can still put uilab on sys.path and
    # import the fixture; then pytest_addoption never ran and this option does
    # not exist.
    return sweep.run(project, driver_name=_driver_name(request))


def _driver_name(request):
    # Defensive lookup, see uilab_sweep: the fixture may be IMPORTED into a
    # module rather than registered through the entry point, in which case
    # pytest_addoption never ran and this option does not exist.
    try:
        return request.config.getoption("--uilab-driver")
    except ValueError:
        return None


@pytest.fixture
def uilab_sweep_at(request):
    """Sweep ONE viewport of the module's project: `uilab_sweep_at(viewport)`.

    The per-viewport shape. Parametrise a test over `sweep.derived_matrix`
    with `ids=sweep.viewport_key`, sweep the one viewport it was handed, and
    judge new defects plus `assert_no_stale_exemptions(..., viewport=...)`
    on that result; pair it with `assert_exemptions_name_live_viewports` so a
    row naming a dead viewport is still caught. Each case is its own unit of
    work, which is what lets a parallel runner spread a 26-viewport sweep
    across 26 workers instead of holding it as one three-minute test (the
    shape sm64_tracker's suite hit its floor on, 2026-09-01). Skipping is the
    same EXPLICIT decision as `uilab_sweep`'s.
    """
    if os.environ.get(SKIP_ENV) == "1":
        pytest.skip(f"{SKIP_ENV}=1 — layout sweep deliberately disabled")
    project = _project(request)
    driver_name = _driver_name(request)

    def run(viewport):
        return sweep.run(project, viewports=[viewport], driver_name=driver_name)
    return run


def assert_no_new_defects(project, result) -> None:
    new = sweep.new_defects(project, result)
    assert not new, (
        f"{len(new)} NEW layout defect(s):\n  "
        + "\n  ".join(f"{key}\n      {detail}"
                      for key, detail in sorted(new.items())[:25]))


def assert_no_stale_exemptions(project, result, viewport=None) -> None:
    stale = sweep.stale_exemptions(project, result, viewport=viewport)
    where = f" at {sweep.viewport_key(viewport)}" if viewport else ""
    assert not stale, (
        f"Fixed{where}, but still exempted — remove {len(stale)} row(s) from "
        f"known_defects: {stale[:8]}")


def assert_exemptions_name_live_viewports(project) -> None:
    """The per-viewport shape's other half: a row naming a viewport outside
    the matrix is one no per-viewport case will ever judge. Needs no browser."""
    orphaned = sweep.exemptions_outside_matrix(project)
    assert not orphaned, (
        f"{len(orphaned)} known_defects row(s) name a viewport the matrix no "
        f"longer contains, so nothing can ever find them stale: {orphaned[:8]}")

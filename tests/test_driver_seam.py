"""The swap-a-better-tool property, enforced rather than asked for.

Everything above the driver seam must speak the `Page` protocol and nothing
else. The moment a probe, a sweep or a gate imports a browser library directly,
replacing that library stops being one module's problem and becomes a rewrite —
and it happens one convenience at a time, each of which looks harmless.

A README sentence cannot fail a build. This can.
"""
import re
from pathlib import Path

import pytest

UILAB = Path(__file__).resolve().parents[1] / "uilab"

# Libraries that would tie the module to one browser tool.
BROWSER_LIBS = ("playwright", "selenium", "puppeteer", "pyppeteer", "helium")

# The only file allowed to import one. Adding a driver adds a row here, which
# is a deliberate, reviewed act rather than an accident.
DRIVER_MODULES = {"drivers/playwright_driver.py"}


def _python_sources():
    return sorted(path for path in UILAB.rglob("*.py")
                  if "__pycache__" not in path.parts)


def _imports(source: str) -> set[str]:
    """Real import statements only.

    Deliberately not a substring scan: `from uilab.drivers import
    playwright_driver` contains the text "import playwright" and is not an
    import of playwright. A grep for that exact string produced a false
    positive the first time this was checked by hand, which is precisely why
    the check is a parsed one and lives in a test.
    """
    found = set()
    for line in source.splitlines():
        match = re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w.]*)", line)
        if match:
            found.add(match.group(1).split(".")[0])
    return found


@pytest.mark.parametrize("path", _python_sources(), ids=lambda p: p.name)
def test_only_a_driver_module_imports_a_browser_library(path):
    relative = path.relative_to(UILAB).as_posix()
    offending = _imports(path.read_text(encoding="utf-8")) & set(BROWSER_LIBS)
    if relative in DRIVER_MODULES:
        return
    assert not offending, (
        f"uilab/{relative} imports {sorted(offending)}. Only "
        f"{sorted(DRIVER_MODULES)} may — everything else speaks the Page "
        f"protocol, which is what makes swapping the browser tool one file "
        f"instead of a rewrite.")


def test_the_guard_can_still_fail():
    """Mutation proof, both directions: a real import is caught, and a mention
    inside another module name is not."""
    assert _imports("import playwright") & set(BROWSER_LIBS)
    assert _imports("from playwright.sync_api import sync_playwright") & set(BROWSER_LIBS)
    assert not _imports("from uilab.drivers import playwright_driver") & set(BROWSER_LIBS)
    assert not _imports("# we used to import playwright here") & set(BROWSER_LIBS)


def test_every_declared_driver_module_exists():
    """A row naming a file that is gone exempts nothing and looks healthy."""
    for relative in DRIVER_MODULES:
        assert (UILAB / relative).exists(), f"{relative} is listed but missing"

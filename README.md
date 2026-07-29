# uilab

Browser instrumentation for UI, CSS and layout work. One shared module for
every project on this machine, so the tooling is researched and improved in a
single place.

Three things it does:

- **Sweep** every breakpoint the stylesheet declares — both sides of each — and
  report overflow, clipping, truncation, overlap, and decorations painting onto
  a box they do not own.
- **Explain** why a CSS property is not what you wrote: matched rules straight
  from the style engine, *plus* the layout override that the cascade alone
  cannot account for.
- **Reach a state on purpose.** Declare the component states worth measuring
  instead of hoping the current data produces them.

## Use it

```python
# myapp/uilab_project.py
from pathlib import Path
from uilab import Project, Story
from myapp.fixture import serve            # yields a base URL

PROJECT = Project(
    serve=serve,
    page_path="/ui/index.html",
    stylesheet=Path("src/myapp/ui/index.html"),
    shell_selectors=("app-", "nav-", "sidebar-"),
    never_truncate=(".field-label",),
    extra_viewports=((900, 1180), (760, 1180)),
    stories=[Story(name="card-populated", at=".card",
                   setup="document.querySelector('#seed').click()")],
)
```

```python
# tests/test_layout.py
from myapp.uilab_project import PROJECT
from uilab.pytest_plugin import assert_no_new_defects, assert_no_stale_exemptions

uilab_project = PROJECT

def test_no_layout_defects(uilab_sweep):
    assert_no_new_defects(PROJECT, uilab_sweep)

def test_exemptions_are_not_stale(uilab_sweep):
    assert_no_stale_exemptions(PROJECT, uilab_sweep)
```

Debugging one property, interactively:

```python
from uilab import explain
from uilab.driver import get_driver

with PROJECT.open() as url, get_driver().launch() as page:
    page.goto(url)
    print(explain(page, ".card", "height"))
```

```
height on .card
  used value:     300px
  winning rule:   50%
  ** the cascade chose '50%' but the used value is '300px', so the cascade has
     stopped being the explanation. Usual suspects: an automatic minimum size
     on a flex/grid item, a percentage resolved against an auto-sized
     ancestor, ...
  matching rules, least specific first:
    .box  =>  80%
    .box  =>  50%
```

## Install

Editable, from one source tree — there is no version to pin and no update step:

```
uv pip install --python ".venv\Scripts\python.exe" -e <path-to-uilab> -e . pytest
python -m playwright install chromium
```

Name `uilab` as an ordinary dependency in the consumer's `pyproject.toml` with
no `[tool.uv.sources]` entry: an absolute path publishes a home directory, a
relative one cannot serve both a checkout and a git worktree several levels
deeper, and a git URL installs a copy and ends the live-edit property this
arrangement exists for.

The other half of that bargain — a change here is live everywhere immediately,
so it can break a consumer immediately:

```
uv run python tools/check_consumers.py
```

Adding a project is one entry in `consumers.json`.

## Swapping the browser tool

Playwright is today's answer, not a commitment. Exactly one module imports it
(`uilab/drivers/playwright_driver.py`); everything above the seam speaks the
`Driver`/`Page` protocol in `uilab/driver.py`. A replacement is a new module
that registers itself, and then a green run of
`tests/test_driver_conformance.py` — which is what makes "swappable" a
checkable claim rather than an aspiration.

Why the current choice, what it beat, and the concrete failures that decided
it: [`docs/decisions.md`](docs/decisions.md).

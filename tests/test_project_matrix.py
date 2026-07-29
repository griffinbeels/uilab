"""What the viewport matrix is derived from, and what a project may refuse."""
from pathlib import Path

from uilab import sweep
from uilab.project import Project, stylesheet_paths


def _noop_serve():
    raise AssertionError("the matrix is derived without opening anything")


def test_default_points_are_included_by_default():
    labels = {view.label for view in sweep.derived_matrix(Project(serve=_noop_serve))}
    assert "wcag-reflow" in labels


def test_a_fixed_geometry_project_can_refuse_the_defaults():
    """A recording rig is not a responsive web app. game-learnings' column
    grid RAISES "viewport too narrow" below its minimum by design, so probing
    320px ships a guaranteed failure — and the only other way to land that is
    a permanent known_defects row, which is a lie about what is broken."""
    project = Project(serve=_noop_serve,
                      include_default_viewports=False,
                      extra_viewports=((2560, 1440), (1920, 1080)))
    assert [(view.width, view.height)
            for view in sweep.derived_matrix(project)] == [(2560, 1440), (1920, 1080)]


def test_thresholds_are_still_derived_when_defaults_are_refused(tmp_path):
    """Refusing the defaults must not refuse the project's own breakpoints —
    otherwise the flag silently turns the sweep into hand-picked widths, which
    is the failure derived_matrix exists to prevent."""
    sheet = tmp_path / "app.css"
    sheet.write_text("@media (max-width: 760px) { .a { color: red } }",
                     encoding="utf-8")
    project = Project(serve=_noop_serve, stylesheet=sheet,
                      include_default_viewports=False)
    widths = {view.width for view in sweep.derived_matrix(project)}
    assert {760, 761} <= widths, widths


def test_stylesheet_accepts_several_files(tmp_path):
    """A workbench's chrome is split across a layout sheet, a component sheet
    and a theme sheet; a matrix from only the first has holes in it."""
    first, second = tmp_path / "a.css", tmp_path / "b.css"
    first.write_text("@media (max-width: 500px) { .a { color: red } }", encoding="utf-8")
    second.write_text("@media (max-width: 900px) { .b { color: blue } }", encoding="utf-8")
    project = Project(serve=_noop_serve, stylesheet=[first, second],
                      include_default_viewports=False)
    widths = {view.width for view in sweep.derived_matrix(project)}
    assert {500, 501, 900, 901} <= widths, widths


def test_stylesheet_paths_normalises_a_single_path(tmp_path):
    sheet = tmp_path / "one.css"
    sheet.write_text("", encoding="utf-8")
    assert stylesheet_paths(Project(serve=_noop_serve, stylesheet=sheet)) == [sheet]
    assert stylesheet_paths(Project(serve=_noop_serve)) == []

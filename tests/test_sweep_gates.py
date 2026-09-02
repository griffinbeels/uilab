"""The two gates a sweep result is judged by, and the shape that lets a
consumer run them ONE VIEWPORT AT A TIME.

Why per-viewport exists: sm64_tracker's whole-matrix sweep was one test of
26 viewports x 15 stories with a 320 ms settle before every probe -- 179 s,
the longest unit in a suite of 8,763 tests, and therefore the floor under any
parallel run of it (2026-09-01). Defect keys already begin with the viewport,
so each viewport's case can judge its own new defects and its own stale
exemptions with nothing gathered across cases. The one thing a per-viewport
case cannot see is an exemption naming a viewport the matrix no longer
contains; `exemptions_outside_matrix` is that check, browser-free.
"""
from uilab import sweep
from uilab.project import Project


def _noop_serve():
    raise AssertionError("nothing here opens a page")


WIDE = sweep.Viewport(1920, 1080, "desktop")
NARROW = sweep.Viewport(850, 1000, "floor")

RESULT = {"defects": {
    "1920x1080 [page] overlap :: span.a x span.b": "overlap 7x2px",
    "850x1000 [page] clipped :: div.card": "clipped 3px",
}, "viewports": 2, "stories": 1, "shots": []}


def test_the_viewport_key_is_the_prefix_every_defect_key_starts_with():
    assert sweep.viewport_key(WIDE) == "1920x1080"
    assert all(key.startswith(sweep.viewport_key(WIDE) + " ")
               or key.startswith(sweep.viewport_key(NARROW) + " ")
               for key in RESULT["defects"])


def test_new_defects_are_the_ones_not_exempted():
    project = Project(serve=_noop_serve, known_defects={
        "1920x1080 [page] overlap :: span.a x span.b": "owed"})
    assert list(sweep.new_defects(project, RESULT)) == [
        "850x1000 [page] clipped :: div.card"]


def test_stale_exemptions_over_the_whole_result():
    project = Project(serve=_noop_serve, known_defects={
        "1920x1080 [page] overlap :: span.a x span.b": "still true",
        "1920x1080 [page] clipped :: div.gone": "fixed last week",
        "850x1000 [page] overlap :: div.gone2": "fixed too"})
    assert sweep.stale_exemptions(project, RESULT) == [
        "1920x1080 [page] clipped :: div.gone",
        "850x1000 [page] overlap :: div.gone2"]


def test_stale_exemptions_at_one_viewport_judge_only_that_viewports_rows():
    """A per-viewport case's result holds only its own viewport's defects, so
    judging every exemption against it would call every OTHER viewport's row
    stale. Restricted to the rows naming this viewport, it is exact."""
    project = Project(serve=_noop_serve, known_defects={
        "1920x1080 [page] overlap :: span.a x span.b": "still true",
        "1920x1080 [page] clipped :: div.gone": "fixed last week",
        "850x1000 [page] overlap :: div.gone2": "not this case's business"})
    wide_only = {"defects": {
        "1920x1080 [page] overlap :: span.a x span.b": "overlap 7x2px"}}
    assert sweep.stale_exemptions(project, wide_only, viewport=WIDE) == [
        "1920x1080 [page] clipped :: div.gone"]
    # A width that merely PREFIXES another (1920 vs 19200) is not confused.
    project2 = Project(serve=_noop_serve, known_defects={
        "19200x1080 [page] overlap :: x": "other viewport"})
    assert sweep.stale_exemptions(project2, wide_only, viewport=WIDE) == []


def test_an_exemption_naming_a_viewport_outside_the_matrix_is_reported():
    """No per-viewport case would ever judge it, so it would sit there
    forever -- which is exactly the lie the stale gate exists to stop."""
    project = Project(serve=_noop_serve, include_default_viewports=False,
                      extra_viewports=((1920, 1080),),
                      known_defects={
                          "1920x1080 [page] overlap :: a": "in the matrix",
                          "1234x1000 [page] overlap :: b": "no such viewport"})
    assert sweep.exemptions_outside_matrix(project) == [
        "1234x1000 [page] overlap :: b"]

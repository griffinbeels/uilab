"""The rules every consuming project inherits.

Instruments measure; laws say what a measurement must not show. They live here
so a rule paid for once in one project is enforced in all of them — which is
the reason this module exists at all rather than being a browser wrapper.

Adding a law is one function here plus one line in a consumer's test module.

Every law states in its own docstring what it structurally CANNOT catch. A
guard whose blind spots are undocumented gets trusted past its range, which is
worse than no guard: it converts "we did not check" into "we checked".
"""
from __future__ import annotations

import re

import pytest

from uilab import css
from uilab.project import stylesheet_paths

# A state a rule can be in that a base rule is not: hover, focus, and the class
# names projects actually use for open/active. Kept literal rather than "any
# compound selector", because a more specific PLAIN selector (.card.featured)
# legitimately declares its own transition — that is a different element, not
# the same element in another state.
_STATE = re.compile(
    r":hover\b|:focus\b|:focus-visible\b|:focus-within\b|:active\b|:checked\b"
    r"|\[aria-\w+\s*=|\.(?:open|active|expanded|collapsed|minimized|minimised"
    r"|maximized|maximised|selected|current|on|off|dragging|hidden|visible)\b")

# The SHORTHAND only. `transition-delay` and `transition-duration` refine an
# inherited shorthand rather than replacing it, so flagging them would fail
# exactly the stylesheets that get this right.
_SHORTHAND = re.compile(r"(?:^|[;{\s])transition\s*:")


def transition_replacement_violations(css_text: str) -> list[str]:
    """State blocks that re-declare the `transition` shorthand.

    CSS `transition` is not additive across rules. A higher-specificity
    `:hover`/`:focus`/state block declaring its own `transition` WHOLESALE
    REPLACES the base rule's, so the animated property silently loses its
    transition exactly while the state is active and regains it on exit. The
    symptom is an asymmetry — smooth in one direction, a snap in the other —
    under CSS that reads as identical, which is why it survives review and
    then gets diagnosed as a duration problem.

    A state block must set target VALUES only.

    What this cannot catch:
      - `transition-property` in a state block, which narrows the property
        list without replacing the shorthand. Rarer, and flagging it produced
        false positives on legitimate refinements.
      - A `transition` set from JavaScript or in a style attribute.
      - A `display` toggle, which cannot animate at all because `display` is
        not interpolable. Different rule, different check, and lengthening the
        duration will never fix it.
    """
    return [f"{line}: {selector}"
            for selector, body, line in css.leaf_rules(css_text)
            if _SHORTHAND.search(body) and _STATE.search(selector)]


def assert_one_transition_declaration(project) -> None:
    """Every state change animates, in both directions, or it is a defect.

    Griffin, 2026-07-26: "we should always prefer animations for changes
    between states ALWAYS. It's more fun!" — which this protects by catching
    the specific way a correct-looking stylesheet stops honouring it.
    """
    texts = _stylesheet_texts(project)
    if not texts:
        pytest.skip("project declares no stylesheet")
    allowed = set(getattr(project, "legacy_transition_rules", ()) or ())
    found = [violation
             for text in texts
             for violation in transition_replacement_violations(text)
             if violation not in allowed]
    assert not found, (
        "These state blocks re-declare the `transition` shorthand, which "
        "WHOLESALE REPLACES the base rule's — the property loses its "
        "transition while the state is active and regains it on exit, so it "
        "animates one way and snaps the other. Set target values only:\n  "
        + "\n  ".join(found))


def assert_components_use_container_queries(project) -> None:
    """`@media` styles the shell; component layout gates on `@container`.

    Viewport width is the wrong signal for a component whenever a shell element
    changes size at a breakpoint: the pane a card lives in is then NOT monotonic
    in window width, and no viewport threshold can express "this card is too
    narrow" — every one of them is wrong on one side of the jump.

    What this cannot catch: a project with no `@media` blocks at all passes
    trivially. That is silence, not coverage.
    """
    if not project.stylesheet or not project.shell_selectors:
        pytest.skip("project declares no stylesheet or no shell selectors")
    shell = tuple(project.shell_selectors)
    violations = [
        f"{block.condition} :: {selector}"
        for text in _stylesheet_texts(project)
        for block in css.size_blocks(css.parse_blocks(text))
        if block.kind == "media"
        for selector in block.selectors
        if not css.is_shell(selector, shell)]
    allowed = set(getattr(project, "legacy_viewport_rules", ()) or ())
    found = [violation for violation in violations if violation not in allowed]
    assert not found, (
        "These @media rules style component-internal selectors; component "
        "layout must gate on @container against its own pane:\n  "
        + "\n  ".join(found))


def _stylesheet_texts(project) -> list[str]:
    return [css.stylesheet_text(path) for path in stylesheet_paths(project)]

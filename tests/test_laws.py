"""The laws every project inherits, and the traps each one has to survive."""
from uilab import css, laws

COMPLIANT = """
/* One transition declaration on the element; the open state sets target
   values only, so it cannot wholesale-replace this. Note this comment quotes
   `transition: opacity 200ms` and `:hover` on purpose — a comment is not
   code, and a scanner that reads this sentence as a rule is broken. */
.panel {
  opacity: 0;
  transition: opacity 180ms cubic-bezier(0.4, 0, 0.2, 1),
              transform 180ms cubic-bezier(0.4, 0, 0.2, 1);
}
.panel.open { opacity: 1; transform: translateY(0); }
.panel.open { transition-delay: 0s; }
.chip:hover { color: var(--tk-ink); }
"""

VIOLATING = """
.band {
  height: 40px;
  transition: height 240ms ease-out;
}
.band:hover {
  height: 120px;
  transition: height 240ms ease-out;
}
"""


def test_a_compliant_stylesheet_reports_nothing():
    assert laws.transition_replacement_violations(COMPLIANT) == []


def test_a_state_block_redeclaring_the_shorthand_is_a_violation():
    found = laws.transition_replacement_violations(VIOLATING)
    assert len(found) == 1, found
    assert ".band:hover" in found[0], found


def test_a_comment_quoting_css_is_not_code():
    """The trap css.py was written around. Stylesheets explain themselves by
    quoting real rules, and a naive scan reads the sentence as a block."""
    quoted = """
    /* Moved out of `.thing:hover { transition: all 200ms; }` because the
       pane there is 725px wide. */
    .thing { transition: opacity 100ms; }
    """
    assert laws.transition_replacement_violations(quoted) == []


def test_a_longhand_in_a_state_block_is_allowed():
    """`transition-delay` and `transition-duration` do NOT replace the
    shorthand — they refine it. Flagging them would fail the very stylesheets
    that get this right, and a law with false positives gets switched off."""
    longhand = """
    .rail { transition: transform 240ms ease-out; }
    .rail.minimized { transform: translateY(90%); transition-delay: 0s, 0s, 240ms; }
    """
    assert laws.transition_replacement_violations(longhand) == []


def test_violations_name_the_selector_s_own_line():
    """Not the line above it. The captured selector text starts at the
    previous rule's closing brace, so the obvious count sends a reader to a
    `}` to look for a bug that is one line further down."""
    assert laws.transition_replacement_violations(VIOLATING) == ["6: .band:hover"]


def test_a_plain_compound_selector_is_not_a_state():
    """`.card.featured` is a different element, not the same element in
    another state, and it may legitimately declare its own transition. A law
    that flagged it would be telling people to break working CSS."""
    compound = """
    .card { transition: opacity 100ms; }
    .card.featured { transition: opacity 400ms; }
    """
    assert laws.transition_replacement_violations(compound) == []


def test_leaf_rules_does_not_mistake_an_at_rule_header_for_a_selector():
    nested = "@media (max-width: 500px) { .card { height: 80px; } }"
    rules = css.leaf_rules(nested)
    assert len(rules) == 1
    assert rules[0][0] == ".card"

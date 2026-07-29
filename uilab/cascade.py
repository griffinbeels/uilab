"""Answer "why is this property not what I wrote?" — from the engine.

The bug this exists for, in full, because it is the expensive shape:

A card would not collapse. The rule matched, `var()` resolved to 52px, it had
the highest specificity and came last in the stylesheet — and the used height
stayed 458px. An INLINE `height: 52px !important` was ignored too. Hours went
into hand-rolled walks over `document.styleSheets`, one of which reported
"0 rules examined" out of 1164, because with CSS Nesting every CSSStyleRule
carries an empty-but-truthy `cssRules` list and `if (rule.cssRules) recurse`
therefore skips every real rule.

Two rules encoded here, and the second is the one nothing else does:

  1. Never re-implement the cascade. `CSS.getMatchedStylesForNode` asks the
     style engine, which is the only thing that knows.

  2. The cascade is not the whole answer. When the winning declaration and the
     USED value disagree, layout has overridden the cascade and no amount of
     specificity will help — say so, and name the remedy. A tool that reports
     only the matched rules leaves a reader concluding the browser is broken,
     which is exactly where those hours went.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Explanation:
    selector: str
    prop: str
    used: str                       # what the element actually ends up with
    declared: str | None            # what the winning rule asked for
    rules: list[dict]               # cascade order, least specific first
    layout_note: str = ""           # set when layout overrode the cascade

    def __str__(self) -> str:
        lines = [f"{self.prop} on {self.selector}",
                 f"  used value:     {self.used}",
                 f"  winning rule:   {self.declared or '(none — initial value)'}"]
        if self.layout_note:
            lines.append(f"  ** {self.layout_note}")
        lines.append("  matching rules, least specific first:")
        for rule in self.rules:
            condition = f"[{rule['condition']}] " if rule["condition"] else ""
            important = " !important" if rule["important"] else ""
            lines.append(f"    {condition}{rule['selector']}"
                         f"  =>  {rule['value']}{important}")
        return "\n".join(lines)


_LAYOUT_QUERY = """
(() => {
  const el = document.querySelector(%(sel)s);
  if (!el) return null;
  const parent = el.parentElement;
  const own = getComputedStyle(el);
  const par = parent ? getComputedStyle(parent) : null;
  return {
    used: own.getPropertyValue(%(propName)s),
    display: par ? par.display : "",
    alignItems: par ? par.alignItems : "",
    alignSelf: own.alignSelf,
    minHeight: own.minHeight,
    overflow: own.overflow,
    contentOverflows: el.scrollHeight > el.clientHeight + 1,
  };
})()
"""


def explain(page, selector: str, prop: str) -> Explanation:
    """Why `prop` on `selector` is what it is."""
    import json
    rules = page.matched_styles(selector, prop)
    layout = page.evaluate(_LAYOUT_QUERY % {
        "sel": json.dumps(selector), "propName": json.dumps(prop)})
    if layout is None:
        raise LookupError(f"no element matches {selector!r}")

    used = str(layout.get("used", ""))
    declared = rules[-1]["value"] if rules else None
    note = ""
    if declared and used and _normalise(declared) != _normalise(used):
        note = _layout_note(prop, declared, used, layout)
    return Explanation(selector, prop, used, declared, rules, note)


def _layout_note(prop: str, declared: str, used: str, layout: dict) -> str:
    """Why the used value differs from the winning declaration.

    Ordered by how often each actually bites, and every branch names the
    REMEDY — an explanation without one just relocates the confusion.
    """
    head = (f"the cascade chose {declared!r} but the used value is {used!r}, "
            f"so the cascade has stopped being the explanation. ")
    parent = layout.get("display", "")
    box = "height" if "height" in prop else "width"

    if parent in ("grid", "flex") and layout.get("contentOverflows") \
            and layout.get("minHeight") == "auto":
        return head + (
            f"This element is a {parent} item, and a {parent} item's AUTOMATIC "
            f"MINIMUM SIZE (`min-{box}: auto`) floors it at its content size — "
            f"so a smaller {prop} is ignored however specific the rule, inline "
            f"`!important` included. Remedy: `min-{box}: 0` on the item, or "
            f"`overflow: hidden`, which also disables the automatic minimum.")

    if parent in ("grid", "flex") \
            and layout.get("alignSelf") in ("auto", "normal", "stretch") \
            and _normalise(declared) == "auto":
        return head + (
            f"This element is a {parent} item with no definite {box}, so it is "
            f"being STRETCHED to its track. Remedy: `align-self: start`, or "
            f"give it a definite {box}.")

    return head + (
        "Usual suspects: an automatic minimum size on a flex/grid item, a "
        "percentage resolved against an auto-sized ancestor, an intrinsic "
        "content minimum, or a transition still in flight — the computed value "
        "mid-transition is the animated one, not the target.")


def _normalise(value: str) -> str:
    return value.strip().rstrip(";").replace(" ", "").lower()

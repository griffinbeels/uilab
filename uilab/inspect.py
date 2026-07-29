"""What an element actually IS, right now — measured, not described in prose.

The sibling of `explain()`. `explain` answers "why is this property that
value"; this answers "what is this element", and it carries the two facts a
browser's own style panel will not tell you:

  topmost_at_centre   — an element can be perfectly styled, correctly
                        positioned and completely unreachable, and every
                        property you inspect looks right. This names whatever
                        would actually receive the click.

  clipped_by_own_box  — an overflow:hidden box cutting its own content off
                        looks identical to one that fits, in a screenshot and
                        in a style panel alike.

Deliberately NOT a Driver protocol verb. It is JS through `evaluate`, exactly
like probes.js, because driver.py's own docstring says that anything a probe
needs which is not already on the protocol is a sign the protocol is wrong —
not an invitation to widen it.
"""
from __future__ import annotations

import json

_DESCRIBE_JS = """
(() => {
  const node = document.querySelector(%(sel)s);
  if (!node) return null;
  const style = getComputedStyle(node);
  const rect = node.getBoundingClientRect();
  const centre = document.elementFromPoint(
    rect.left + rect.width / 2, rect.top + rect.height / 2);
  // classList, not className: an SVG element's className is an
  // SVGAnimatedString that stringifies to "[object SVGAnimatedString]" and
  // makes every report about a chart unreadable.
  const name = (el) => el
    ? el.tagName.toLowerCase()
      + (el.id ? "#" + el.id : "")
      + (el.classList && el.classList.length
          ? "." + Array.from(el.classList).join(".") : "")
    : "(nothing — outside the viewport)";
  return {
    box: rect.width || rect.height
      ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
      : null,
    text: (node.textContent || "").trim().slice(0, 120),
    font: style.fontSize + " / " + style.lineHeight
          + " " + style.fontFamily.split(",")[0],
    color: style.color,
    background: style.backgroundColor,
    display: style.display,
    visibility: style.visibility,
    opacity: style.opacity,
    overflow: style.overflow,
    zIndex: style.zIndex,
    clipped_by_own_box: node.scrollHeight > node.clientHeight + 1
                     || node.scrollWidth > node.clientWidth + 1,
    topmost_at_centre: centre === node || node.contains(centre)
      ? "this element"
      : name(centre),
  };
})()
"""


def describe(page, selector: str) -> dict:
    """Everything objectively true about the one element `selector` names."""
    found = page.evaluate(_DESCRIBE_JS % {"sel": json.dumps(selector)})
    if found is None:
        raise LookupError(f"no element matches {selector!r}")
    return {"selector": selector, **found}

// uilab layout probes — measured in the page, returned as plain JSON.
//
// Semantic assertions, never pixel diffing. A screenshot baseline goes red for
// a clock tick, a hover, an animation frame or a font-rendering change, and the
// literature on visual regression is mostly about fighting that flake. These
// need no baseline, survive dynamic content, and each result NAMES the defect
// instead of reporting that 37 pixels differ.
//
// Defines one global: __uilab(config) -> {overflow, clipped, truncated, overlap}.
(() => {
  const EPS = 1.5;                       // sub-pixel layout noise

  // SVG elements carry an SVGAnimatedString in .className, which stringifies to
  // "[object SVGAnimatedString]" and makes every chart defect unreadable.
  // classList works in both namespaces.
  const path = (el) => {
    if (el.id) return "#" + el.id;
    const cls = Array.from(el.classList || []).slice(0, 3).join(".");
    return el.tagName.toLowerCase() + (cls ? "." + cls : "");
  };

  const visible = (el) => {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (parseFloat(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  // Visually-hidden text is clipped ON PURPOSE — that IS the technique. Without
  // this, .sr-only fires at every viewport and the noise gets the whole probe
  // exemption-listed into uselessness.
  const clippedByDesign = (style) =>
    style.clip !== "auto" || style.clipPath !== "none";

  const scrollableAncestor = (el) => {
    for (let node = el.parentElement; node; node = node.parentElement)
      if (["auto", "scroll"].includes(getComputedStyle(node).overflowX)) return true;
    return false;
  };

  window.__uilab = (config) => {
    const cfg = config || {};
    const root = cfg.at ? document.querySelector(cfg.at) : document.body;
    if (!root) return {error: "scope selector matched nothing: " + cfg.at};
    const neverTruncate = cfg.neverTruncate || [];
    const out = {overflow: [], clipped: [], truncated: [], overlap: []};
    const all = Array.from(root.querySelectorAll("*")).filter(visible);

    // 1. Content escaping the viewport sideways — measured by GEOMETRY.
    //    `document.scrollWidth` is useless on any page that sets
    //    `overflow-x: hidden`, which is most of them: the page then cannot grow
    //    a scrollbar and scrollWidth never exceeds innerWidth however far
    //    content escapes. Verified: a deliberately injected 5000px child moved
    //    it by exactly zero. getBoundingClientRect still sees the escape.
    for (const el of all) {
      if (el.children.length > 0) continue;          // leaves only: one report per escape
      const style = getComputedStyle(el);
      if (clippedByDesign(style) || style.position === "fixed") continue;
      if (scrollableAncestor(el)) continue;          // legitimate: it can be scrolled to
      const rect = el.getBoundingClientRect();
      if (rect.width === 0) continue;
      if (rect.right - window.innerWidth > EPS)
        out.overflow.push({selector: path(el), detail:
          "right edge " + Math.round(rect.right) + " past viewport " + window.innerWidth});
      else if (rect.left < -EPS)
        out.overflow.push({selector: path(el), detail:
          "left edge " + Math.round(rect.left) + " before viewport origin"});
    }

    // 2. Content clipped inside an overflow:hidden box — the silent one. Both
    //    end states look correct in a screenshot; only the measurement shows
    //    that the bottom of the card is being cut off.
    for (const el of all) {
      const style = getComputedStyle(el);
      if (clippedByDesign(style)) continue;
      const hiddenY = style.overflowY === "hidden" || style.overflow === "hidden";
      const hiddenX = style.overflowX === "hidden" || style.overflow === "hidden";
      if (hiddenY && el.scrollHeight - el.clientHeight > EPS)
        out.clipped.push({selector: path(el), detail:
          "scrollHeight " + el.scrollHeight + " > clientHeight " + el.clientHeight});
      // A horizontal clip is only a defect when nothing is ellipsising: a
      // truncated label is a deliberate, legible outcome; a hard cut is not.
      if (hiddenX && el.scrollWidth - el.clientWidth > EPS
          && style.textOverflow !== "ellipsis")
        out.clipped.push({selector: path(el), detail:
          "scrollWidth " + el.scrollWidth + " > clientWidth " + el.clientWidth});
    }

    // 3. Opted-in elements that are truncating. Opting IN is deliberate — a
    //    blanket "nothing may ellipsise" fires on every intentional
    //    text-overflow in the app.
    for (const selector of neverTruncate)
      for (const el of root.querySelectorAll(selector)) {
        if (!visible(el)) continue;
        if (el.scrollWidth - el.clientWidth > EPS)
          out.truncated.push({selector, detail:
            '"' + el.textContent.trim().slice(0, 40) + '" truncated'});
      }

    // 4. Overlap between NORMAL-FLOW siblings. Narrow on purpose: absolutely
    //    positioned things, negative margins and decorative washes overlap by
    //    design, and inside an SVG overlapping geometry IS the point — a
    //    chart's line crosses its own gridlines.
    for (const parent of all) {
      if (parent.ownerSVGElement || parent.tagName.toLowerCase() === "svg") continue;
      const kids = Array.from(parent.children).filter((kid) => {
        if (!visible(kid)) return false;
        if (!["static", "relative"].includes(getComputedStyle(kid).position)) return false;
        return !kid.hasAttribute("data-uilab-allow-overlap");
      });
      for (let i = 0; i < kids.length; i++)
        for (let j = i + 1; j < kids.length; j++) {
          const a = kids[i].getBoundingClientRect();
          const b = kids[j].getBoundingClientRect();
          const dx = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const dy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          if (dx > EPS && dy > EPS)
            out.overlap.push({selector: path(kids[i]) + " x " + path(kids[j]),
              detail: "overlap " + Math.round(dx) + "x" + Math.round(dy)
                      + "px inside " + path(parent)});
        }
    }
    return out;
  };
})();

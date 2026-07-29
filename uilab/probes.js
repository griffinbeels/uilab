// uilab layout probes — measured in the page, returned as plain JSON.
//
// Semantic assertions, never pixel diffing. A screenshot baseline goes red for
// a clock tick, a hover, an animation frame or a font-rendering change, and the
// literature on visual regression is mostly about fighting that flake. These
// need no baseline, survive dynamic content, and each result NAMES the defect
// instead of reporting that 37 pixels differ.
//
// Defines one global:
//   __uilab(config) -> {overflow, clipped, truncated, overlap, decoration}.
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

  const TRANSPARENT = /^(transparent|rgba\(0,\s*0,\s*0,\s*0\))$/;

  // A pseudo-element has no DOM node, so nothing that walks the tree can see
  // it -- but an ABSOLUTELY POSITIONED one has fully resolved used values, and
  // its containing block is its host's padding box whenever the host is itself
  // positioned. That makes its painted rect derivable, which is the whole
  // reason this probe can exist.
  const decorationRect = (host, pseudo) => {
    const style = getComputedStyle(host, pseudo);
    if (style.content === "none" || style.content === "normal") return null;
    if (style.display === "none" || style.visibility === "hidden") return null;
    if (parseFloat(style.opacity) === 0) return null;
    if (style.position !== "absolute") return null;   // only these are derivable
    // Ink, not just geometry: a transparent spacer pseudo overlapping something
    // is invisible, and reporting it would drown the real ones.
    if (style.backgroundImage === "none" && TRANSPARENT.test(style.backgroundColor))
      return null;
    const hostStyle = getComputedStyle(host);
    if (hostStyle.position === "static") return null;  // containing block is elsewhere
    const box = host.getBoundingClientRect();
    const num = (value) => parseFloat(value) || 0;
    const top = box.top + num(hostStyle.borderTopWidth)
              + num(style.top) + num(style.marginTop);
    const left = box.left + num(hostStyle.borderLeftWidth)
               + num(style.left) + num(style.marginLeft);
    // getComputedStyle resolves width/height to the CONTENT box.
    const width = num(style.width) + num(style.paddingLeft) + num(style.paddingRight)
                + num(style.borderLeftWidth) + num(style.borderRightWidth);
    const height = num(style.height) + num(style.paddingTop) + num(style.paddingBottom)
                 + num(style.borderTopWidth) + num(style.borderBottomWidth);
    if (![top, left, width, height].every(Number.isFinite)) return null;
    if (width <= 0 || height <= 0) return null;
    return {top, left, right: left + width, bottom: top + height};
  };

  // Something a decoration landing on top of would actually be SEEN to cover.
  // An empty layout wrapper is not; a box with its own paint or its own words
  // is. Without this the probe reports every bleed into a structural div.
  const rendersInk = (el) => {
    const style = getComputedStyle(el);
    if (style.backgroundImage !== "none") return true;
    if (!TRANSPARENT.test(style.backgroundColor)) return true;
    for (const side of ["Top", "Right", "Bottom", "Left"])
      if (parseFloat(style["border" + side + "Width"]) > 0
          && !TRANSPARENT.test(style["border" + side + "Color"])) return true;
    for (const node of el.childNodes)
      if (node.nodeType === 3 && node.textContent.trim()) return true;
    return false;
  };

  window.__uilab = (config) => {
    const cfg = config || {};
    const root = cfg.at ? document.querySelector(cfg.at) : document.body;
    if (!root) return {error: "scope selector matched nothing: " + cfg.at};
    const neverTruncate = cfg.neverTruncate || [];
    // Elements whose whole PURPOSE is to hide their content: a collapsed
    // panel, a clamped preview, a peeking drawer. Without this the sweep
    // reports every one of them as a clipping defect the moment a project
    // gains a collapse control -- 108 of them in one run, all correct
    // behaviour. Declared by the project, because only it knows which of its
    // overflow:hidden boxes are deliberate.
    const mayClip = cfg.mayClip || [];
    const clipAllowed = (el) => mayClip.some((sel) => el.matches(sel));
    // Hosts whose decoration is MEANT to cross other boxes: a scrim behind a
    // modal, a focus ring drawn outside its control, a full-bleed hero wash.
    const mayBleed = cfg.mayBleed || [];
    const out = {overflow: [], clipped: [], truncated: [], overlap: [],
                 decoration: []};
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
      if (clippedByDesign(style) || clipAllowed(el)) continue;
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

    // 5. Decorations painting onto a box that is not their own.
    //
    //    Class 4 above deliberately skips these -- "decorative washes overlap
    //    by design" -- and that exclusion is exactly what hid two real bugs
    //    for four rounds each (sm64_tracker, 2026-07-28/29). A rank banner's
    //    ::before wash bled -16px sideways across a divider onto the PB tag,
    //    and bled -8px/-12px vertically onto the banner stacked beneath it,
    //    covering it. Both were reported by the user, repeatedly, while every
    //    sweep read the page as clean: a pseudo-element is absent from the
    //    DOM, so no probe that walks the tree can ever see one.
    //
    //    The law is not "a decoration may not leave its host" -- bleeding into
    //    an ancestor's own padding or grid gap is the normal, correct reason
    //    to write one. It is: a decoration may not cover a box that is neither
    //    its host nor inside it. Ancestors are that host's own space;
    //    everything else belongs to something else.
    const related = (host, other) => host === other
      || host.contains(other) || other.contains(host);

    // One report per collided SUBTREE, not per inky leaf inside it. The
    // stacked banners hit each other through eleven descendants -- five hat
    // layers, the name, the delta, the progress track and its fill -- which is
    // one bug wearing eleven costumes. The box actually being covered is the
    // outermost ancestor of the hit that is still unrelated to the host.
    const collisionOwner = (host, other) => {
      let owner = other;
      while (owner.parentElement && !related(host, owner.parentElement))
        owner = owner.parentElement;
      return owner;
    };

    // A fixed or sticky element floats over page content on purpose -- that is
    // what it is FOR, and scrolling puts it over something at every offset.
    const floats = (el) => {
      for (let node = el; node; node = node.parentElement)
        if (["fixed", "sticky"].includes(getComputedStyle(node).position)) return true;
      return false;
    };

    for (const host of all) {
      if (mayBleed.some((sel) => host.matches(sel))) continue;
      for (const pseudo of ["::before", "::after"]) {
        const wash = decorationRect(host, pseudo);
        if (!wash) continue;
        const hits = new Map();
        for (const other of all) {
          if (related(host, other)) continue;
          if (!rendersInk(other) || floats(other)) continue;
          const box = other.getBoundingClientRect();
          const dx = Math.min(wash.right, box.right) - Math.max(wash.left, box.left);
          const dy = Math.min(wash.bottom, box.bottom) - Math.max(wash.top, box.top);
          if (dx <= EPS || dy <= EPS) continue;
          const owner = collisionOwner(host, other);
          const worst = hits.get(owner);
          if (!worst || dx * dy > worst.dx * worst.dy) hits.set(owner, {dx, dy});
        }
        for (const [owner, {dx, dy}] of hits)
          out.decoration.push({selector: path(host) + pseudo + " over " + path(owner),
            detail: "decoration covers " + Math.round(dx) + "x" + Math.round(dy)
                    + "px of a box it does not own"});
      }
    }
    return out;
  };
})();

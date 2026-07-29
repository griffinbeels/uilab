// uilab frame trace — record what moves, every frame, in the page.
//
// Defines two globals:
//   __uilabTraceStart(config) -> true      begin recording
//   __uilabTraceRead()        -> {frames}  stop and hand back what was recorded
//
// Why an in-page recorder: NOT because evaluate() cannot await a rAF walker —
// it can, measured. Because an awaited one holds the driver for the whole
// window, and record() has to fire the trigger and take screenshots inside it.
// Recording here and reading the array ONCE afterwards is what lets the numbers
// and the strip describe the same run. Full reasoning in trace.py's docstring.
(() => {
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };

  // The 2D affine pieces, pulled out of a computed `matrix(...)`/`matrix3d(...)`
  // so a caller can ask about translation and scale without parsing strings.
  // Anything unparseable comes back null rather than 0 — a real 0 and "no
  // transform" are different answers and conflating them hides a bug.
  const decompose = (transform) => {
    if (!transform || transform === "none") return { x: 0, y: 0, scaleX: 1, scaleY: 1 };
    const inside = transform.slice(transform.indexOf("(") + 1, -1).split(",").map(Number);
    if (transform.startsWith("matrix3d") && inside.length === 16) {
      return { x: inside[12], y: inside[13],
               scaleX: Math.hypot(inside[0], inside[1]),
               scaleY: Math.hypot(inside[4], inside[5]) };
    }
    if (inside.length === 6) {
      return { x: inside[4], y: inside[5],
               scaleX: Math.hypot(inside[0], inside[1]),
               scaleY: Math.hypot(inside[2], inside[3]) };
    }
    return { x: null, y: null, scaleX: null, scaleY: null };
  };

  // EFFECTIVE opacity, not the element's own. A parent's opacity multiplies
  // every child's, so an element reporting 1 can still be invisible — which is
  // exactly how a card "briefly became invisible" while its own opacity rule
  // said otherwise, for a whole review round.
  const effectiveOpacity = (el) => {
    let value = 1;
    for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
      const own = parseFloat(getComputedStyle(node).opacity);
      if (Number.isFinite(own)) value *= own;
    }
    return value;
  };

  const sample = (selector, extras) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    const out = {
      x: box.x, y: box.y, width: box.width, height: box.height,
      opacity: num(style.opacity),
      effectiveOpacity: effectiveOpacity(el),
      color: style.color,
      background: style.backgroundColor,
      text: (el.textContent || "").trim().slice(0, 60),
      ...decompose(style.transform),
    };
    for (const prop of extras || []) {
      out[prop] = style.getPropertyValue(prop).trim();
    }
    return out;
  };

  window.__uilabTraceStart = (config) => {
    const watch = config.watch || {};
    const extras = config.properties || [];
    const frames = [];
    const t0 = performance.now();
    let stopped = false;
    const tick = () => {
      const at = performance.now() - t0;
      const row = { t: Math.round(at * 100) / 100 };
      for (const [name, selector] of Object.entries(watch)) {
        row[name] = sample(selector, extras);
      }
      frames.push(row);
      if (!stopped && at < config.ms) requestAnimationFrame(tick);
    };
    window.__uilabTraceRead = () => { stopped = true; return { frames }; };
    requestAnimationFrame(tick);
    return true;
  };
})();

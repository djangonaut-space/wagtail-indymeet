/*! @viselect/vanilla v3.9.0 MIT | https://github.com/Simonwep/selection/tree/master/packages/vanilla */
class X {
  constructor() {
    this._listeners = /* @__PURE__ */ new Map(), this.on = this.addEventListener, this.off = this.removeEventListener, this.emit = this.dispatchEvent;
  }
  addEventListener(e, t) {
    const s = this._listeners.get(e) ?? /* @__PURE__ */ new Set();
    return this._listeners.set(e, s), s.add(t), this;
  }
  removeEventListener(e, t) {
    var s;
    return (s = this._listeners.get(e)) == null || s.delete(t), this;
  }
  dispatchEvent(e, ...t) {
    let s = !0;
    for (const i of this._listeners.get(e) ?? [])
      s = i(...t) !== !1 && s;
    return s;
  }
  unbindAllListeners() {
    this._listeners.clear();
  }
}
const L = (l, e = "px") => typeof l == "number" ? l + e : l, y = ({ style: l }, e, t) => {
  if (typeof e == "object")
    for (const [s, i] of Object.entries(e))
      i !== void 0 && (l[s] = L(i));
  else t !== void 0 && (l[e] = L(t));
}, M = (l = 0, e = 0, t = 0, s = 0) => {
  const i = { x: l, y: e, width: t, height: s, top: e, left: l, right: l + t, bottom: e + s };
  return { ...i, toJSON: () => JSON.stringify(i) };
}, Y = (l) => {
  let e, t = -1, s = !1;
  return {
    next: (...i) => {
      e = i, s || (s = !0, t = requestAnimationFrame(() => {
        l(...e), s = !1;
      }));
    },
    cancel: () => {
      cancelAnimationFrame(t), s = !1;
    }
  };
}, k = (l, e, t = "touch") => {
  switch (t) {
    case "center": {
      const s = e.left + e.width / 2, i = e.top + e.height / 2;
      return s >= l.left && s <= l.right && i >= l.top && i <= l.bottom;
    }
    case "cover":
      return e.left >= l.left && e.top >= l.top && e.right <= l.right && e.bottom <= l.bottom;
    case "touch":
      return l.right >= e.left && l.left <= e.right && l.bottom >= e.top && l.top <= e.bottom;
  }
}, H = () => matchMedia("(hover: none), (pointer: coarse)").matches, N = () => "safari" in window, A = (l) => Array.isArray(l) ? l : [l], O = (l) => (e, t, s, i = {}) => {
  (e instanceof HTMLCollection || e instanceof NodeList) && (e = Array.from(e)), t = A(t), e = A(e);
  for (const o of e)
    if (o)
      for (const n of t)
        o[l](n, s, { capture: !1, ...i });
}, S = O("addEventListener"), g = O("removeEventListener"), x = (l) => {
  var i;
  const { clientX: e, clientY: t, target: s } = ((i = l.touches) == null ? void 0 : i[0]) ?? l;
  return { x: e, y: t, target: s };
}, E = (l, e = document) => A(l).map(
  (t) => typeof t == "string" ? Array.from(e.querySelectorAll(t)) : t instanceof Element ? t : null
).flat().filter(Boolean), q = (l, e) => e.some((t) => typeof t == "number" ? l.button === t : typeof t == "object" ? t.button !== l.button ? !1 : t.modifiers.every((s) => {
  switch (s) {
    case "alt":
      return l.altKey;
    case "ctrl":
      return l.ctrlKey || l.metaKey;
    case "shift":
      return l.shiftKey;
  }
}) : !1), { abs: b, max: C, min: B, ceil: R } = Math, D = (l = []) => ({
  stored: l,
  selected: [],
  touched: [],
  changed: { added: [], removed: [] }
}), T = class T extends X {
  constructor(e) {
    var o, n, r, a, u;
    super(), this._selection = D(), this._targetBoundaryScrolled = !0, this._selectables = [], this._areaLocation = { y1: 0, x2: 0, y2: 0, x1: 0 }, this._areaRect = M(), this._singleClick = !0, this._scrollAvailable = !0, this._scrollingActive = !1, this._scrollSpeed = { x: 0, y: 0 }, this._scrollDelta = { x: 0, y: 0 }, this._lastMousePosition = { x: 0, y: 0 }, this.enable = this._toggleStartEvents, this.disable = this._toggleStartEvents.bind(this, !1), this._options = {
      selectionAreaClass: "selection-area",
      selectionContainerClass: void 0,
      selectables: [],
      document: window.document,
      startAreas: ["html"],
      boundaries: ["html"],
      container: "body",
      ...e,
      behaviour: {
        overlap: "invert",
        intersect: "touch",
        triggers: [0],
        ...e.behaviour,
        startThreshold: (o = e.behaviour) != null && o.startThreshold ? typeof e.behaviour.startThreshold == "number" ? e.behaviour.startThreshold : { x: 10, y: 10, ...e.behaviour.startThreshold } : { x: 10, y: 10 },
        scrolling: {
          speedDivider: 10,
          manualSpeed: 750,
          ...(n = e.behaviour) == null ? void 0 : n.scrolling,
          startScrollMargins: {
            x: 0,
            y: 0,
            ...(a = (r = e.behaviour) == null ? void 0 : r.scrolling) == null ? void 0 : a.startScrollMargins
          }
        }
      },
      features: {
        range: !0,
        touch: !0,
        deselectOnBlur: !1,
        ...e.features,
        singleTap: {
          allow: !0,
          intersect: "native",
          ...(u = e.features) == null ? void 0 : u.singleTap
        }
      }
    };
    for (const _ of Object.getOwnPropertyNames(Object.getPrototypeOf(this)))
      typeof this[_] == "function" && (this[_] = this[_].bind(this));
    const { document: t, selectionAreaClass: s, selectionContainerClass: i } = this._options;
    this._area = t.createElement("div"), this._clippingElement = t.createElement("div"), this._clippingElement.appendChild(this._area), this._area.classList.add(s), i && this._clippingElement.classList.add(i), y(this._area, {
      willChange: "top, left, bottom, right, width, height",
      top: 0,
      left: 0,
      position: "fixed"
    }), y(this._clippingElement, {
      overflow: "hidden",
      position: "fixed",
      transform: "translate3d(0, 0, 0)",
      // https://stackoverflow.com/a/38268846
      pointerEvents: "none",
      zIndex: "1"
    }), this._frame = Y((_) => {
      this._recalculateSelectionAreaRect(), this._updateElementSelection(), this._emitEvent("move", _), this._redrawSelectionArea();
    }), this.enable();
  }
  _toggleStartEvents(e = !0) {
    const { document: t, features: s } = this._options, i = e ? S : g;
    i(t, "mousedown", this._onTapStart), s.touch && i(t, "touchstart", this._onTapStart, { passive: !1 });
  }
  _onTapStart(e, t = !1) {
    const { x: s, y: i, target: o } = x(e), { document: n, startAreas: r, boundaries: a, features: u, behaviour: _ } = this._options, c = o.getBoundingClientRect();
    if (e instanceof MouseEvent && !q(e, _.triggers))
      return;
    const p = E(r, n), m = E(a, n);
    this._targetElement = m.find(
      (v) => k(v.getBoundingClientRect(), c)
    );
    const f = e.composedPath(), d = p.find((v) => f.includes(v));
    if (this._targetBoundary = m.find((v) => f.includes(v)), !this._targetElement || !d || !this._targetBoundary || !t && this._emitEvent("beforestart", e) === !1)
      return;
    this._areaLocation = { x1: s, y1: i, x2: 0, y2: 0 };
    const h = n.scrollingElement ?? n.body;
    this._scrollDelta = { x: h.scrollLeft, y: h.scrollTop }, this._singleClick = !0, this.clearSelection(!1, !0), S(n, ["touchmove", "mousemove"], this._delayedTapMove, { passive: !1 }), S(n, ["mouseup", "touchcancel", "touchend"], this._onTapStop), S(n, "scroll", this._onScroll), u.deselectOnBlur && (this._targetBoundaryScrolled = !1, S(this._targetBoundary, "scroll", this._onStartAreaScroll));
  }
  _onSingleTap(e) {
    const { singleTap: { intersect: t }, range: s } = this._options.features, i = x(e);
    let o;
    if (t === "native")
      o = i.target;
    else if (t === "touch") {
      this.resolveSelectables();
      const { x: r, y: a } = i;
      o = this._selectables.find((u) => {
        const { right: _, left: c, top: p, bottom: m } = u.getBoundingClientRect();
        return r < _ && r > c && a < m && a > p;
      });
    }
    if (!o)
      return;
    for (this.resolveSelectables(); !this._selectables.includes(o); )
      if (o.parentElement)
        o = o.parentElement;
      else {
        this._targetBoundaryScrolled || this.clearSelection();
        return;
      }
    const { stored: n } = this._selection;
    if (this._emitEvent("start", e), e.shiftKey && s && this._latestElement) {
      const r = this._latestElement, [a, u] = r.compareDocumentPosition(o) & 4 ? [o, r] : [r, o], _ = [...this._selectables.filter(
        (c) => c.compareDocumentPosition(a) & 4 && c.compareDocumentPosition(u) & 2
      ), a, u];
      this.select(_), this._latestElement = r;
    } else n.includes(o) && (n.length === 1 || e.ctrlKey || n.every((r) => this._selection.stored.includes(r))) ? this.deselect(o) : (this.select(o), this._latestElement = o);
  }
  _delayedTapMove(e) {
    const { container: t, document: s, behaviour: { startThreshold: i } } = this._options, { x1: o, y1: n } = this._areaLocation, { x: r, y: a } = x(e);
    if (
      // Single number for both coordinates
      typeof i == "number" && b(r + a - (o + n)) >= i || // Different x and y threshold
      typeof i == "object" && b(r - o) >= i.x || b(a - n) >= i.y
    ) {
      if (g(s, ["mousemove", "touchmove"], this._delayedTapMove, { passive: !1 }), this._emitEvent("beforedrag", e) === !1) {
        g(s, ["mouseup", "touchcancel", "touchend"], this._onTapStop);
        return;
      }
      S(s, ["mousemove", "touchmove"], this._onTapMove, { passive: !1 }), y(this._area, "display", "block"), E(t, s)[0].appendChild(this._clippingElement), this.resolveSelectables(), this._singleClick = !1, this._targetRect = this._targetElement.getBoundingClientRect(), this._scrollAvailable = this._targetElement.scrollHeight !== this._targetElement.clientHeight || this._targetElement.scrollWidth !== this._targetElement.clientWidth, this._scrollAvailable && (S(this._targetElement, "wheel", this._wheelScroll, { passive: !1 }), S(this._options.document, "keydown", this._keyboardScroll, { passive: !1 }), this._selectables = this._selectables.filter((u) => this._targetElement.contains(u))), this._setupSelectionArea(), this._emitEvent("start", e), this._onTapMove(e);
    }
    this._handleMoveEvent(e);
  }
  _setupSelectionArea() {
    const { _clippingElement: e, _targetElement: t, _area: s } = this, i = this._targetRect = t.getBoundingClientRect();
    this._scrollAvailable ? (y(e, {
      top: i.top,
      left: i.left,
      width: i.width,
      height: i.height
    }), y(s, {
      marginTop: -i.top,
      marginLeft: -i.left
    })) : (y(e, {
      top: 0,
      left: 0,
      width: "100%",
      height: "100%"
    }), y(s, {
      marginTop: 0,
      marginLeft: 0
    }));
  }
  _onTapMove(e) {
    const { _scrollSpeed: t, _areaLocation: s, _options: i, _frame: o } = this, { speedDivider: n } = i.behaviour.scrolling, r = this._targetElement, { x: a, y: u } = x(e);
    if (s.x2 = a, s.y2 = u, this._lastMousePosition.x = a, this._lastMousePosition.y = u, this._scrollAvailable && !this._scrollingActive && (t.y || t.x)) {
      this._scrollingActive = !0;
      const _ = () => {
        if (!t.x && !t.y) {
          this._scrollingActive = !1;
          return;
        }
        const { scrollTop: c, scrollLeft: p } = r;
        t.y && (r.scrollTop += R(t.y / n), s.y1 -= r.scrollTop - c), t.x && (r.scrollLeft += R(t.x / n), s.x1 -= r.scrollLeft - p), o.next(e), requestAnimationFrame(_);
      };
      requestAnimationFrame(_);
    } else
      o.next(e);
    this._handleMoveEvent(e);
  }
  _handleMoveEvent(e) {
    const { features: t } = this._options;
    (t.touch && H() || this._scrollAvailable && N()) && e.preventDefault();
  }
  _onScroll() {
    const { _scrollDelta: e, _options: { document: t } } = this, { scrollTop: s, scrollLeft: i } = t.scrollingElement ?? t.body;
    this._areaLocation.x1 += e.x - i, this._areaLocation.y1 += e.y - s, e.x = i, e.y = s, this._setupSelectionArea(), this._frame.next(null);
  }
  _onStartAreaScroll() {
    this._targetBoundaryScrolled = !0, g(this._targetElement, "scroll", this._onStartAreaScroll);
  }
  _wheelScroll(e) {
    const { manualSpeed: t } = this._options.behaviour.scrolling, s = e.deltaY ? e.deltaY > 0 ? 1 : -1 : 0, i = e.deltaX ? e.deltaX > 0 ? 1 : -1 : 0;
    this._scrollSpeed.y += s * t, this._scrollSpeed.x += i * t, this._onTapMove(e), e.preventDefault();
  }
  _keyboardScroll(e) {
    const { manualSpeed: t } = this._options.behaviour.scrolling, s = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0, i = e.key === "ArrowUp" ? -1 : e.key === "ArrowDown" ? 1 : 0;
    this._scrollSpeed.x += Math.sign(s) * t, this._scrollSpeed.y += Math.sign(i) * t, e.preventDefault(), this._onTapMove({
      clientX: this._lastMousePosition.x,
      clientY: this._lastMousePosition.y,
      preventDefault: () => {
      }
    });
  }
  _recalculateSelectionAreaRect() {
    const { _scrollSpeed: e, _areaLocation: t, _targetElement: s, _options: i } = this, { scrollTop: o, scrollHeight: n, clientHeight: r, scrollLeft: a, scrollWidth: u, clientWidth: _ } = s, c = this._targetRect, { x1: p, y1: m } = t;
    let { x2: f, y2: d } = t;
    const { behaviour: { scrolling: { startScrollMargins: h } } } = i;
    f < c.left + h.x ? (e.x = a ? -b(c.left - f + h.x) : 0, f = f < c.left ? c.left : f) : f > c.right - h.x ? (e.x = u - a - _ ? b(c.left + c.width - f - h.x) : 0, f = f > c.right ? c.right : f) : e.x = 0, d < c.top + h.y ? (e.y = o ? -b(c.top - d + h.y) : 0, d = d < c.top ? c.top : d) : d > c.bottom - h.y ? (e.y = n - o - r ? b(c.top + c.height - d - h.y) : 0, d = d > c.bottom ? c.bottom : d) : e.y = 0;
    const v = B(p, f), w = B(m, d), j = C(p, f), K = C(m, d);
    this._areaRect = M(v, w, j - v, K - w);
  }
  _redrawSelectionArea() {
    const { x: e, y: t, width: s, height: i } = this._areaRect, { style: o } = this._area;
    o.left = `${e}px`, o.top = `${t}px`, o.width = `${s}px`, o.height = `${i}px`;
  }
  _onTapStop(e, t) {
    var n;
    const { document: s, features: i } = this._options, { _singleClick: o } = this;
    g(this._targetElement, "scroll", this._onStartAreaScroll), g(s, ["mousemove", "touchmove"], this._delayedTapMove), g(s, ["touchmove", "mousemove"], this._onTapMove), g(s, ["mouseup", "touchcancel", "touchend"], this._onTapStop), g(s, "scroll", this._onScroll), this._keepSelection(), e && o && i.singleTap.allow ? this._onSingleTap(e) : !o && !t && (this._updateElementSelection(), this._emitEvent("stop", e)), this._scrollSpeed.x = 0, this._scrollSpeed.y = 0, g(this._targetElement, "wheel", this._wheelScroll, { passive: !0 }), g(this._options.document, "keydown", this._keyboardScroll, { passive: !0 }), this._clippingElement.remove(), (n = this._frame) == null || n.cancel(), y(this._area, "display", "none");
  }
  _updateElementSelection() {
    const { _selectables: e, _options: t, _selection: s, _areaRect: i } = this, { stored: o, selected: n, touched: r } = s, { intersect: a, overlap: u } = t.behaviour, _ = u === "invert", c = [], p = [], m = [];
    for (let d = 0; d < e.length; d++) {
      const h = e[d];
      if (k(i, h.getBoundingClientRect(), a)) {
        if (n.includes(h))
          o.includes(h) && !r.includes(h) && r.push(h);
        else if (_ && o.includes(h)) {
          m.push(h);
          continue;
        } else
          p.push(h);
        c.push(h);
      }
    }
    _ && p.push(...o.filter((d) => !n.includes(d)));
    const f = u === "keep";
    for (let d = 0; d < n.length; d++) {
      const h = n[d];
      !c.includes(h) && !// Check if the user wants to keep previously selected elements, e.g.,
      // not make them part of the current selection as soon as they're touched.
      (f && o.includes(h)) && m.push(h);
    }
    s.selected = c, s.changed = { added: p, removed: m }, this._latestElement = void 0;
  }
  _emitEvent(e, t) {
    return this.emit(e, {
      event: t,
      store: this._selection,
      selection: this
    });
  }
  _keepSelection() {
    const { _options: e, _selection: t } = this, { selected: s, changed: i, touched: o, stored: n } = t, r = s.filter((a) => !n.includes(a));
    switch (e.behaviour.overlap) {
      case "drop": {
        t.stored = [
          ...r,
          ...n.filter((a) => !o.includes(a))
          // Elements not touched
        ];
        break;
      }
      case "invert": {
        t.stored = [
          ...r,
          ...n.filter((a) => !i.removed.includes(a))
          // Elements not removed from selection
        ];
        break;
      }
      case "keep": {
        t.stored = [
          ...n,
          ...s.filter((a) => !n.includes(a))
          // Newly added
        ];
        break;
      }
    }
  }
  /**
   * Manually triggers the start of a selection
   * @param evt A MouseEvent / TouchEvent-like object
   * @param silent If beforestart should be fired
   */
  trigger(e, t = !0) {
    this._onTapStart(e, t);
  }
  /**
   * Can be used if during a selection elements have been added
   * Will update everything that can be selected
   */
  resolveSelectables() {
    this._selectables = E(this._options.selectables, this._options.document);
  }
  /**
   * Same as deselecting, but for all elements currently selected
   * @param includeStored If the store should also get cleared
   * @param quiet If move / stop events should be fired
   */
  clearSelection(e = !0, t = !1) {
    const { selected: s, stored: i, changed: o } = this._selection;
    o.added = [], o.removed.push(
      ...s,
      ...e ? i : []
    ), t || (this._emitEvent("move", null), this._emitEvent("stop", null)), this._selection = D(e ? [] : i);
  }
  /**
   * @returns {Array} Selected elements
   */
  getSelection() {
    return this._selection.stored;
  }
  /**
   * @returns {HTMLElement} The selection area element
   */
  getSelectionArea() {
    return this._area;
  }
  /**
   * @returns {Element[]} Available selectable elements for current selection
   */
  getSelectables() {
    return this._selectables;
  }
  /**
   * Set the location of the selection area
   * @param location A partial AreaLocation object
   */
  setAreaLocation(e) {
    Object.assign(this._areaLocation, e), this._redrawSelectionArea();
  }
  /**
   * @returns {AreaLocation} The current location of the selection area
   */
  getAreaLocation() {
    return this._areaLocation;
  }
  /**
   * Cancel the current selection process, pass true to fire a stop event after cancel
   * @param keepEvent If a stop event should be fired
   */
  cancel(e = !1) {
    this._onTapStop(null, !e);
  }
  /**
   * Unbinds all events and removes the area-element.
   */
  destroy() {
    this.cancel(), this.disable(), this._clippingElement.remove(), super.unbindAllListeners();
  }
  /**
   * Adds elements to the selection
   * @param query CSS Query, can be an array of queries
   * @param quiet If this should not trigger the move event
   */
  select(e, t = !1) {
    const { changed: s, selected: i, stored: o } = this._selection, n = E(e, this._options.document).filter(
      (r) => !i.includes(r) && !o.includes(r)
    );
    return o.push(...n), i.push(...n), s.added.push(...n), s.removed = [], this._latestElement = void 0, t || (this._emitEvent("move", null), this._emitEvent("stop", null)), n;
  }
  /**
   * Removes a particular element from the selection
   * @param query CSS Query, can be an array of queries
   * @param quiet If this should not trigger the move event
   */
  deselect(e, t = !1) {
    const { selected: s, stored: i, changed: o } = this._selection, n = E(e, this._options.document).filter(
      (r) => s.includes(r) || i.includes(r)
    );
    this._selection.stored = i.filter((r) => !n.includes(r)), this._selection.selected = s.filter((r) => !n.includes(r)), this._selection.changed.added = [], this._selection.changed.removed.push(
      ...n.filter((r) => !o.removed.includes(r))
    ), this._latestElement = void 0, t || (this._emitEvent("move", null), this._emitEvent("stop", null));
  }
};
T.version = "3.9.0";
let P = T;
export {
  P as default
};
//# sourceMappingURL=viselect.mjs.map

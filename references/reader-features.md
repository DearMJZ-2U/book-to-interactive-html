# Reader features

The four controls every book needs, and the bug each one shipped with.
Working implementations live in `assets/reader.css` and `assets/reader.js`.

---

## 1. Table of contents

**Ship a panel, not a `<select>`.** The `<select>` version reset itself to
`""` after every choice, so the control was blank on return, and its rounded
bordered pill read as a search box (E1).

- The button shows the **current chapter**, so it is never empty.
- The panel lists every section: `●` current, `✓` already passed.
- Click-outside and `Esc` close it.
- Long jumps are instant, short hops glide (D12, E6).

Chapter labels come from the assembler, not from parsing `h1` (E2):

```python
for cid, (num, rest) in TOCINFO.items():
    body, k = re.subn(r'(<section class="chapter" id="%s")' % cid,
                      r'\1 data-toc="%s" data-tt="%s"' % (num, rest), body, count=1)
    if not k: missed.append(cid)          # assert, never assume
```

After a jump, update the label **immediately** — don't wait for the scroll
event, or the button lags a frame behind.

## 2. Full-text search

Index elements that have their **own** direct text child; that avoids
parent/child double counting while still matching across inline markup:

```js
var SEL = "p, li, td, th, h1, h2, h3, figcaption, cite, .chart-cap, text";
CH.forEach(function (c) {
  c.el.querySelectorAll(SEL).forEach(function (el) {
    var own = false;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.nodeValue.replace(/\s+/g, "")) { own = true; break; }
    }
    if (!own) return;
    var t = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (t.length < 2) return;
    INDEX.push({ el: el, lc: t.toLowerCase(), ch: c });
  });
});
```

Build it lazily on first open — a 280 000 px document is expensive to index up front.

**Highlighting must handle matches split across text nodes** (E3):

```js
var nodes = [], text = "";
var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), n;
while ((n = w.nextNode())) { nodes.push({ node: n, start: text.length }); text += n.nodeValue; }
var i = text.toLowerCase().indexOf(q);
function locate(pos) {
  for (var k = 0; k < nodes.length; k++) {
    var end = nodes[k].start + nodes[k].node.nodeValue.length;
    if (pos < end || (pos === end && k === nodes.length - 1))
      return { node: nodes[k].node, off: pos - nodes[k].start };
  }
  var last = nodes[nodes.length - 1];
  return { node: last.node, off: last.node.nodeValue.length };
}
var a = locate(i), b = locate(i + q.length);
var r = document.createRange(); r.setStart(a.node, a.off); r.setEnd(b.node, b.off);
var m = document.createElement("mark"); m.className = "sh";
r.surroundContents(m);          // remember to unwrap it on the next search
```

**SVG cannot take an HTML `<mark>`** (E4) — detect and fall back:
```js
if (el.ownerSVGElement) { el.classList.add("hit-box"); return false; }
```

Also: open ancestor `<details>` before scrolling, or the jump lands on a
collapsed element.

## 3. Night mode

CSS variables flip for the page; **SVG does not** (F1). Recolour at runtime
and cache the originals:

```js
function collectPaint() {
  document.querySelectorAll("svg [fill], svg [stroke]").forEach(function (el) {
    ["fill", "stroke"].forEach(function (a) {
      var v = el.getAttribute(a);
      if (!v || v === "none" || v[0] !== "#") return;
      var key = a === "fill" ? "f" : "s";
      el["_o" + key] = v;                       // original, for the return trip
      paintNodes.push([el, a, key, v]);
    });
  });
  document.querySelectorAll('[style*="--accent"],[style*="--c"]').forEach(function (el) {
    el["_ostyle"] = el.getAttribute("style") || "";
    accentNodes.push(el);
  });
}
```
Attribute selectors match a parent `<g fill>` too — that's why text that
inherits its colour still gets remapped (F3).

Pure lightness inversion is not enough (F2); expand away from the midpoint:

```js
var nl = (1 - L) * 0.92 + 0.04;
nl = 0.5 + (nl - 0.5) * 1.18;      // S-curve
nl = Math.max(0.03, Math.min(0.97, nl));
```

Because a label and the block behind it flip together, both palettes stay
readable — but **verify it**, don't assume. Run the whole chart audit again
under the dark palette and require zero low-contrast.

## 4. Reading position

```js
var LS = (function () {            // file:// can block localStorage
  var mem = {}, ok = true;
  try { localStorage.setItem("__t", "1"); localStorage.removeItem("__t"); }
  catch (e) { ok = false; }        // fall back to an in-memory object
  return {
    get: function (k, d) { try { var v = ok ? localStorage.getItem("hbj:" + k) : mem[k];
                                 return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { var s = JSON.stringify(v);
                                 if (ok) localStorage.setItem("hbj:" + k, s); else mem[k] = s; }
                            catch (e) {} }
  };
})();
```

Throttled save on scroll, plus `beforeunload` and `visibilitychange`:

```js
{ id: chapterId, off: scrollY - chapterTop, y: scrollY, pct: pct, at: Date.now() }
```

Restore with an **instant** jump and a guard on `max(y, off)` (E6, E7):

```js
var depth = Math.max(saved.y || 0, saved.off || 0);
if (depth > 400) {
  document.documentElement.style.scrollBehavior = "auto";
  window.scrollTo({ top: chapterTop + saved.off, behavior: "instant" });
  document.documentElement.style.scrollBehavior = prev;
}
```

Offer a one-click "从头开始" that clears the key — otherwise a reader who
wants the cover is trapped by their own memory.

## Storage discipline

- One key prefix (`hbj:`), everything JSON-encoded.
- Always round-trip through `JSON.stringify` — a raw string breaks the read
  side's `JSON.parse`, and the `catch` turns it into a silent default (E5).
- Test by **pre-seeding before the app's script** runs, with the same encoding.
- Clear state in every audit run, or a dark run leaks into the next light one (D11).
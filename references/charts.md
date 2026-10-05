# Hand-built SVG charts

Charts are hand-authored SVG, not a charting library. Why: a library cannot
produce the hand-drawn look, and a 900-unit `viewBox` scaled to the page is
the only way to keep label size stable across breakpoints.

## The shape

```html
<div class="chartbox">
  <svg class="chart" viewBox="0 0 900 430" role="img"
       aria-label="一句话把这张图讲清楚">
    <!-- shapes first, then text, in one consistent paint order -->
  </svg>
</div>
<p class="chart-cap">图 12｜……（数据来自原书第 X 章）</p>
```

## Rules and the reasons

**`viewBox` width fixed at 900.** Everything scales from it. Changing the
width per chart makes cross-book comparison impossible and breaks the audit's
scale arithmetic.

**No `<rect>`.** Use hand-drawn jittered rounded `<path>`:
```
M357 168 L542 166 Q552 167 550 175 L548 244 Q549 252 542 251 …
```
A 2 px jitter on the corners reads as "drawn", and it avoids the dead
rectangle look. Decorative jitter must never move a point that encodes data.

**All text after all shapes.** Paint order is what the audit uses to resolve
each label's backdrop (D4). Mixing them makes "what is behind this word?"
unanswerable.

**One chapter accent colour per chapter**, via `--accent` on the section:
```html
<section class="chapter" id="ch07" style="--accent:#6E7B2E">
```
Never hardcode a palette constant inside a chart — night mode needs to remap
it (F1).

**Minimum label size 12 units** in a 900-wide viewBox. The audit asserts the
*rendered* size (`units × scale`) stays ≥ 11 px at every breakpoint.

**One chart per row.** A two-column `.figpair` split a 960 px page into
444 px halves — scale 0.493, i.e. 6 px labels (C5). If you must pair
graphics, pair ones without text.

**Never `text-anchor="middle"` for a label that must clear an edge.** For a
left-edge tick, use `text-anchor="start"` and pull `x` inside the viewBox —
`x="120" text-anchor="middle"` on a label starting near the left edge hangs
off the canvas.

## Animation

CSS-only, driven by an IntersectionObserver that adds `.in`:

```css
.chart .draw  { stroke-dasharray: var(--len); stroke-dashoffset: var(--len);
                transition: stroke-dashoffset 1.1s ease; }
.reveal.in .chart .draw { stroke-dashoffset: 0; }
.chart .grow  { transform-box: fill-box; transform-origin: center;
                transform: scaleY(0); transition: transform .9s ease; }
.reveal.in .chart .grow { transform: scaleY(1); }
```
Stagger with `.d1`–`.d4` delay classes. Respect
`@media (prefers-reduced-motion: reduce)` by zeroing every transition.

**Do not put `transform` on `:nth-child` rules for elements that also receive
`.reveal`** — the tilt wins and the entrance animation is skipped (C4).

## The audit will catch

- labels under 11 px rendered
- text overlapping text
- text escaping the viewBox (measured in screen space — D3)
- low contrast against the **opacity-composited** backdrop (D6)
- text swallowed by a later shape (D5)

If it flags something, **open the actual chart source before "fixing" it**.
D6 is the proof: the audit was wrong, and its recommended fix made the page
unreadable.
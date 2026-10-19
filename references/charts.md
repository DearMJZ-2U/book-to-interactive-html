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

---

## Writing 35 charts without losing a day

The 《缠斗》 build hand-authored 35 charts (5 per chapter) and hit every finding
below. What made it tractable:

### Build the geometry once, then vary the data

Every chart uses the same frame: a 900-wide viewBox, a baseline near `y = 350`,
plot height ~270, label column on the left. Decide the frame before writing the
first chart; then each new chart is data points plus labels.

### The jittered-path rectangle

No `<rect>`, so bars and cards are `<path>` with 2-unit corner jitter. Generate
the path from `(x, y, w, h)` rather than hand-typing coordinates — hand-typed
paths drift a pixel or two per chart and the bars start looking uneven:

```
M{x} {y} L{x+w} {y-2} Q{x+w+10} {y-1} {x+w+9} {y+9}
L{x+w+8} {y+h} Q{x+w+9} {y+h+8} {x+w-1} {y+h+9}
L{x} {y+h+2} Q{x-10} {y+h+1} {x-9} {y+h-9}
L{x-8} {y+8} Q{x-9} {y} {x+1} {y} Z
```

### Three findings that cost the most time

**1. A `fill="none"` path is not a colour.** The night-mode probe took
`querySelector("svg.chart [fill]")`, got a line's `fill="none"`, and asserted it
should change when the theme flipped. It never would. Any tool that walks
`[fill]` must skip `none`.

**2. White text on a 60 %-opacity bar is unreadable.** A bar filled `#B5533C`
at `opacity="0.6"` composites to pale pink; white labels on it measured 2.42:1.
Either make the bar opaque or use a dark ink on the pale composite — do not
"fix" it by brightening the text.

**3. `#96877E` on the `#E3D6C4` tint is 2.42:1.** The muted grey works on paper
(`#FBF6EE`) but not on the tinted block. `#7A6C62` clears 3.0:1 on both. When a
chart puts quiet labels inside a tinted panel, darken the grey for that chart
rather than for the whole book.

### Label budget per chart

| Element | Max | Note |
|---|---|---|
| title | 1 | at `y ≈ 42`, `text-anchor="start"`, `x = 110` |
| axis names | 2 | |
| tick labels | ≤8 per axis | thin them rather than shrink below 12 |
| direct labels on data | 4–6 | prefer these over a legend |
| legend entries | ≤4 | only if direct labels are impossible |
| annotation callouts | ≤3 | what makes it a *diagram* rather than a chart |

If a chart needs more than that, it is two charts.

### The one thing worth doing by hand

**Annotation callouts.** A bar chart says "42.58 %". A callout says
"42.58 % — 东亚独大, and the only region that rose". That sentence is the reason
to draw the chart at all, and no generator will write it for you.

### Verify data against the fact pack, not the chart

Every number in a chart must appear in `pack/<CID>.md`. Before shipping, grep the
chart source for digits and check each against the pack. A chart that
mis-states one number is worse than no chart, because it looks authoritative.

### One chart per row, always

`grid-template-columns: 1fr 1fr` splits a 960 px page into 444 px halves, so a
900-unit chart renders at scale 0.49 and 12-unit labels land at 5.9 px (C5).
There is no exception for "small" charts with text on them.
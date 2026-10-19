# Pitfalls — 电子书转 HTML 书踩过的坑

Every entry is a failure that actually happened while building real books.
Format: **symptom → cause → fix**. Grouped by where it bit.

The recurring theme: **silent zeros**. Almost every bug here produced a
plausible-looking success message while the underlying step did nothing.
Always assert a *count*, never just "the script ran".

---

## A. Extraction & data plumbing

### A1. `AttributeError: 'NoneType' object has no attribute 'group'`
**Cause.** `re.match(r"chapter\d+\.txt$", f)` returns `None` for every file
that doesn't match (e.g. `toc.ncx`), then `.group(1)` explodes.
**Fix.** Guard before matching:
```python
m = re.match(r"chapter(\d+)\.txt$", f)
if not m: continue
```

### A2. A generated JSON came out as `{}`
**Cause.** A dict keyed off the filename with an off-by-one slice:
`key = f[:-6]` where the real key is `f[:-5]`. Every lookup missed, so the
output was a valid, empty, completely silent JSON object.
**Fix.** After generating any lookup table, assert `len(table) > 0` and print
a sample key. An empty dict is never a legitimate result here.

### A3. Duplicate figure numbers after merging
**Cause.** Merging per-file figure manifests without deduplicating on number.
**Fix.** Merge same-numbered entries; assert the final count equals the count
of distinct numbers.

---

## B. Subagents

### B1. "Active child" limit (typically 8)
**Cause.** Dispatching one child per chapter for a 13-chapter book.
**Fix.** Serialize dispatches in batches; queue the rest.

### B2. A subagent cannot look at images
**Cause.** The model has no image input.
**Fix.** Never ask a subagent to judge an image. Give it the **caption text**
and let the geometry audit verify the result. Charts must be authored from
numbers in the fact pack, never from looking at a picture.

### B3. A subagent confidently invented two facts I supplied wrongly
**Cause.** I passed plausible-sounding but unverified numbers in the prompt;
the agent elaborated on them.
**Fix.** Pass only what's in `pack/<CID>.md`, and instruct: *"if a fact is
not in the pack, omit it — do not fill the gap."* When an agent pushes back on
a supplied fact, believe it.

### B4. Duplicate note markers inside a quiz answer block
**Cause.** An agent reused a `<sup class="nb">` already present in the body.
**Fix.** `notechk.py` must assert **no duplicate `data-n`**, not just
"every marker has an `<li>`".

---

## C. Assembly

### C1. Output was 25.5 MB instead of 13.8 MB
**Cause.** `data-zoom="data:image/…;base64,…"` attributes duplicated every
image's base64 payload a second time inside the markup.
**Fix.** The lightbox reads `img.src` + `data-cap`; never store the URL in a
second attribute. Assert the file size in `assemble.py` output.

### C2. A normalisation regex fired 0 times
**Cause.** Pattern `[a-z0-9 _-]` — the **space** in the class broke
backtracking, so the alternation never matched multi-word values.
**Fix.** Put the space first or escape it: `[ -~]`, `[\w -]`. **Always print
the match count.** "0 replacements" is a bug until proven otherwise.

### C3. A `<table>` nested inside a `<table>`
**Cause.** Wrapping `<div class="tbl">` with `<table class="tbl">` when the
div already contained an inner `<table>`. The browser hoists the inner table
and leaves an empty, zero-height outer one.
**Fix.** Check for an existing table inside before wrapping; unwrap instead.

### C4. Entrance animations silently skipped
**Cause.** `.card:nth-child(2n){transform:rotate(-.35deg)}` outranks
`.reveal{transform:translateY(22px)}`, so those cards never animate — they
snap upright when `.reveal.in` fires.
**Fix.** Never put `transform` on a `:nth-child` rule that also receives
`.reveal`. Compose the tilt inside the reveal's own transform.

### C5. Charts rendered at 6 px text
**Cause.** `.figpair { grid-template-columns: 1fr 1fr }` split the page width
in two; each 900-unit chart got 444 px → **scale 0.493**.
**Fix.** One chart per row. Side-by-side only for small, non-text graphics.

---

## D. The headless-Chrome audit

This section is the most valuable and the most dangerous: **every item here
produced either a false alarm or a false all-clear.**

### D1. `--dump-dom` returned 0 bytes
**Cause.** PowerShell `>` redirection against Chrome's stdout, or the
console encoding mangling it.
**Fix.** Always shell out through Python:
```python
subprocess.run([CHROME, "--headless", "--dump-dom", url],
               stdout=open(out, "w", encoding="utf-8"),
               stderr=subprocess.DEVNULL)
```

### D2. `TypeError: parameter 1 is not of type 'Element'`
**Cause.** Storing a text string where the script's other branch stored an
element, then calling `.getBBox()` on it.
**Fix.** Always store the element itself (`{b, el, txt, eff, fs}`), never
its text, alongside geometry.

### D3. Rotated labels reported as escaping the viewBox
**Cause.** **`getBBox()` ignores the element's own `transform`.** A label
rotated -55° looks far outside the box in local coordinates while being
perfectly placed on screen.
**Fix.** Measure in screen space with `getBoundingClientRect()`.

### D4. Wrong backdrop resolved for chart text
**Cause.** Picking the first/largest shape under the text. The visible
backdrop is the **last shape painted before the text**.
**Fix.** Build a document-order map and pick the shape with the greatest
order index that is still `<` the text's index.

### D5. "Text hidden behind a shape" fired 25 false positives
**Cause.** Any later shape whose bbox happened to intersect the glyphs.
**Fix.** Require the covering shape to actually swallow the text:
`inter(shapeBox, textBox) / area(textBox) > 0.9` **and** `fillOpacity >= 0.5`.

### D6. ★ Contrast audit ignored `fill-opacity` — caused a real regression
**Cause.** A panel filled `#6E7B2E` at **`opacity=".14"`** over cream paper is
a *pale wash*, not a dark block. The audit read the raw fill and reported
contrast 1.0 against the olive text, so "fixing" it turned the text white —
**white on a pale wash, unreadable in daylight.** The audit had been lying.
**Fix.** Composite the fill over the backdrop before measuring:
```js
var alpha = fillOpacity * opacity;
var eff = alpha >= 0.99 ? fill : over(fill, cardBackground, alpha);
```
This one is the strongest argument for auditing: the tool lied, and I nearly
shipped the damage it caused.

### D7. Charts reported "distorted" that were fine
**Cause.** Scale computed from the **border box** while `.chart` has
`padding` + `border`.
**Fix.**
```js
scale = (r.width - padL - padR - borderL - borderR) / vbWidth;
```
Real value was 0.973, not the 1.009 I had read off a naive measurement.

### D8. "Cramped"/"blank box" fired on every layout-only container
**Cause.** `.cmp`, `.tbl`, `.fig`, `details` legitimately have zero outer
padding and no direct text.
**Fix.** Compute `ownText` from **direct child text nodes only**, and skip
containers that have none.

### D9. "Touching" fired on every block in the document
**Cause.** Taking `min()` over all four sides — the last child always ends
exactly at the content-box bottom, so the gap is always 0.
**Fix.** Measure L/R/T/B separately and flag only **negative** values.

### D10. Chinese output printed as mojibake / emoji crashed the reporter
**Cause.** Windows console defaults to GBK.
**Fix.** `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the
top of any Python script that prints Chinese, or write to a file and read it
back with `Get-Content -Encoding UTF8`.

### D11. ★ A `--dark` run leaked into the next light run
**Cause.** Chrome's `--user-data-dir` persists `localStorage`. A run that
saved `theme=dark` made the *next* run report dark numbers while claiming to
be light — the two audits disagreed and neither was labelled.
**Fix.** Pin the environment explicitly on **every** run, both directions:
```python
pre = '<script>try{localStorage.removeItem("hbj:pos");' \
      'localStorage.setItem("hbj:theme",JSON.stringify("%s"));}catch(e){}</script>' % theme
```
And **print the theme next to every result row.**

### D12. Tests failed because smooth scroll never finished
**Cause.** `--virtual-time-budget` advances timers but not compositor-driven
animations. A probe that clicks a TOC entry then immediately asserts
`pageYOffset` always sees the old value.
**Fix.** In the product code, make long jumps `behavior:"instant"` (a
140 000 px smooth scroll is bad UX anyway). In probes, assert after a delay
or use the instant path.

### D13. Flaky numbers between identical runs
**Cause.** The page restored a saved scroll position, and reveal animations
were caught mid-flight — so a `.reveal.in` element's opacity/transform was
sampled at a random point.
**Fix.** Inject before measuring:
```html
<style>*,*::before,*::after{transition:none!important;animation:none!important}
       html{scroll-behavior:auto!important}</style>
<script>try{localStorage.removeItem("hbj:pos")}catch(e){}</script>
```

### D14. `node --check` on a file containing top-level `return`
**Cause.** `app.js` is an IIFE fragment; checking it standalone fails.
**Fix.** Wrap probe/fragment JS in `(function(){...})()` before syntax
checking, and run the real check in the browser.

---

## E. Reader features

### E1. ★ The TOC select was always blank and looked like a search box
**Cause.** `sel.value = ""` after every selection, so the control showed
nothing on return. A rounded, bordered `<select>` also reads as a search
field — which is exactly the complaint.
**Fix.** Replace it with a real panel. Show the **current chapter** in the
button so it is never empty; list all sections; highlight the current one.

### E2. Chapter numbers came out empty in the TOC
**Cause.** Parsing `h1.textContent` with `/^(引言|第[一二三四五六七八九十]+章)/`
— but the `h1` is `<h1><span class="no">00</span>如果人类的历史…</h1>`, so
the text starts with `00`, not `第一章`.
**Fix.** Make the assembler emit authoritative labels
(`data-toc="第一章" data-tt="合作的生命"`) into the section tag. Single
source of truth beats re-parsing display markup.

### E3. Search found a term but highlighted nothing
**Cause.** `markIn()` searched each text node independently, so a query split
by `<b>` or `<br>` — very common in Chinese copy — matched the joined
`textContent` in the index but matched no single node on the page.
**Fix.** Concatenate all descendant text nodes into one flat string with an
offset map, find the match there, then map back to `(node, offset)` and wrap
with a `Range`.

### E4. Search highlights in chart text silently did nothing
**Cause.** `document.createElement("mark")` inserted into an SVG subtree
creates an invalid HTML element in the SVG namespace.
**Fix.** Detect `el.ownerSVGElement` and fall back to an outline class.

### E5. ★ Theme preference appeared not to persist
**Cause.** My test seeded `localStorage.setItem("hbj:theme", "dark")` while
the app stored `JSON.stringify("dark")` → `'"dark"'`. `JSON.parse("dark")`
throws, the helper's `catch` returned the default, and the app silently
reverted to light.
**Fix.** **The test was wrong, not the app.** Seed values through the same
`JSON.stringify` the app uses. A "bug" that vanishes when you check the test
was always the test.

### E6. Restoring the reading position fired a 140 000 px smooth scroll
**Cause.** Global `html{scroll-behavior:smooth}` applies to
`window.scrollTo({behavior:"auto"})` too.
**Fix.**
```js
document.documentElement.style.scrollBehavior = "auto";
window.scrollTo({ top: Y, behavior: "instant" });
document.documentElement.style.scrollBehavior = prev;
```
Rule of thumb: **glide under ~2400 px, land instantly above it.**

### E7. Position restore silently skipped after a layout change
**Cause.** The restore guard tested `savedPos.y > 400`. If the page grew or
the window widened, `y` could land near 0 while the in-section offset was
still deep.
**Fix.** Guard on `Math.max(savedPos.y || 0, savedPos.off || 0) > 400`.

---

## F. Dark mode

### F1. ★ CSS variables flip; SVG hex does not
83 charts used literal `fill="#6E7D8C"`. Switching `:root` tokens changed
the cards and left every chart on the daylight palette.
**Fix.** Recolour in JS at runtime: walk `svg [fill], svg [stroke]`, convert
to HSL, remap lightness, keep hue, cache the original per attribute so the
toggle is lossless in both directions.

### F2. Plain lightness inversion flattens contrast
**Cause.** `L' = 1 - L` preserves ordering but WCAG luminance is non-linear,
so pairs sitting near mid-grey ended up at 2.70–2.95 instead of ≥ 3.0.
**Fix.** Expand away from the midpoint after inverting:
```js
nl = (1 - L) * 0.92 + 0.04;
nl = 0.5 + (nl - 0.5) * 1.18;   // S-curve restores separation
nl = Math.max(0.03, Math.min(0.97, nl));
```
Result: 4 low-contrast labels → 0.

### F3. Recolouring only presentation attributes misses `<g fill>`
**Cause.** Many labels inherit from a parent `<g fill="…">`.
**Fix.** Select `svg [fill], svg [stroke]` — attribute selectors match the
group too — and store the original on the element that actually owns it.

---

## G. Content integrity

### G1. ★ Regexes that miss attribute order
`<li id="ch05-n3">` found 285 items; the four real misses were
`<li class="ed" id="ch05-n3">`. A regex anchored as `<li id="` silently
under-counts and looks like data loss.
**Fix.** `<li[^>]*id="([^"]+)"`. When a count disagrees with an expectation,
**verify the discrepancy is real before reporting it.**

### G2. "Count preserved" asserted without counting
**Fix.** After every build, re-grep the deliverable for note markers, note
items, images, figures, charts, captions, tables and sections, and diff
against the pre-build numbers. Report the table.

### G3. ★ A colon-space inside a skill description breaks YAML entirely
**Cause.** `description: ... interactive HTML book: per-chapter explanation ...`
In an unquoted YAML scalar, `: ` begins a **mapping**. The frontmatter fails
to parse, the skill silently never loads, and it disappears from the catalog
with no error anywhere.
**Fix.** Never write `: ` inside an unquoted `description:` — use an em dash.
Then **verify**, because a missing catalog entry is the only symptom:
```python
import yaml; t = open("SKILL.md", encoding="utf-8").read()
print(yaml.safe_load(t.split("---")[1]))
```
`scripts/validate_skill.py` in this skill does exactly that check.

### G4. A skill `name` cannot contain capitals
**Cause.** The Agent Skills spec allows *lowercase letters, numbers and
hyphens only*. `Book-to-Interactive-HTML` is rejected or silently renamed.
**Fix.** `book-to-interactive-html`, and the directory name must match.

---

## H. PDF / OCR sources

### H1. A scanned book without `--ocr` yields empty chapters and looks fine
**Cause.** `page.get_text()` returns `''` on an image-only page, so the run
happily writes zero-character "chapters".
**Fix.** `extract_pdf.py` probes the text layer and **refuses to continue**
below 50 % coverage. Do not route around it with `--force` unless you know
only the front matter is an image.

### H2. A missing outline is the normal case, not an error
**Fix.** `get_toc()` returning `[]` is information, not failure — you must
derive the chapter page ranges yourself.

### H3. ★ PDF physical pages ≠ printed page numbers
They differ by the front matter, often by 10–40 pages. Every later
"page N" reference is wrong if you mix them.
**Fix.** Record physical indices (1-based, what `get_text`/`get_pixmap` take),
and record both when you need to cite a printed page.

### H6. ★ Probing only the first pages misclassifies a mixed book
**Cause.** The scan check read pages 1–12. A book with an image cover and
image copyright page has **no text there**, so a perfectly digital body was
declared "scanned" and a digital extraction was refused.
**Fix.** Sample pages **spread across the range actually being extracted** and
judge by ratio, not an absolute threshold. Print the percentage so the
decision is visible.

### H7. ★ RapidOCR rejects raw PNG bytes
**Cause.** `np.frombuffer(pix.tobytes("png"), np.uint8)` yields a 1-D array:
`LoadImageError: The ndim(1) of the img is not in [2, 3]`.
**Fix.** Feed **raw samples**, not an encoded image:
```python
arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
if pix.n == 4: arr = arr[:, :, :3]
```
Measured on this machine: ~7.6 s/page at `dpi=200, threads=4`, plus a one-off
model load. Cache per page so a crash costs one batch, not the book.

### H8. DOCX: paragraphs and tables come out in the wrong order
**Cause.** `doc.paragraphs` and `doc.tables` are separate sequences. Iterating
one then the other pushes every table to the end of the chapter.
**Fix.** Walk `document.element.body` **once**, dispatching on each child's tag.

### H9. DOCX heading styles are localised
`"Heading 1"` vs `"标题 1"`. Check the paragraph's `w:outlineLvl`, then the
style name, then **the style's own** `w:outlineLvl` — python-docx's
`add_heading` puts the level on the *style*, not the paragraph, so a
paragraph-only check silently misses every heading.

### H10. ★ Shadowing a path variable with paragraph text
**Cause.**
```python
txt = os.path.join(raw, "text")   # the output directory
...
for p in ...:
    txt = p.text.strip()           # now it is a string
open(os.path.join(txt, name), "w") # FileNotFoundError on the chapter text
```
**Fix.** Name the loop variable for what it is (`line`). Never reuse a path
variable as a content variable in a long function.

### H11. ★ A helper that only initialises never splits
**Cause.**
```python
def ensure(title):
    if cur is None: cur = new(title)   # only ever creates the FIRST chapter
    return cur
...
if is_heading(p, 1): ensure(line)      # heading 2..N merged into chapter 1
```
**Fix.** A heading must unconditionally **start** a new chapter; `ensure`
is only for leading text that precedes any heading.
Symptom to watch for: the chapter count comes back `1` on a document that
plainly has several headings.

### H12. ★★ A line list is not prose — the fact pack must be rebuilt into paragraphs
**Cause.** The usual OCR recipe sorts boxes by `(round(y/12), x)` and joins with
newlines. That gives lines, and a pack built from it cuts every sentence at the
printed line width:

```
（世界发展指标）数据库的统计，2008年东亚及太平洋地区（含东
南亚）的制造业增加值约占全球的33.94%，中国当时的全球占比
为11.3%；2024年，该地区这一比重增加到42.58%，中国的全球
```

A writer reading that cannot tell a paragraph break from a line wrap, so it
either quotes half a sentence or invents the join. Nothing in the pipeline
catches this: the pack is "complete", every number is present, and the prose
still reads wrong.
**Fix.** Keep each line's `x0`/`x1` and rebuild paragraphs geometrically — a
line that **starts indented** opens a paragraph, a line that **stops short of
the right margin** (and does not end in `，、：（；`) closes one. Joining on
punctuation alone fails on every line that ends mid-clause. `scripts/ocr_lines.py`
does this; build the packs from `raw/paragraphs.txt`.
**Sanity number.** 418 pages → 11 650 lines → **2 552 paragraphs**. If your
paragraph count is near your line count, the rebuild did nothing.

### H13. ★★ Figure and table captions sit on opposite sides of the plate
**Cause.** In 《缠斗》 every 图N.M caption is printed **below** its chart and
every 表N.M caption **above** its table. Hard-coding either convention crops the
wrong side for half the book — and the crops still look plausible, because the
region above a figure caption is usually *some* content.
**Fix.** Propose both sides, bound each by the nearest PROSE line, and let the
caption's own kind decide which side is preferred; ink only breaks ties within
a side. See `scripts/crop_plates.py`.

### H14. ★★ "Long line" is not "prose" — it puts the crop edge through the axis labels
**Cause.** A chart's tick row (`51015202530354045…`) and its axis caption are
long, wide and start near the margin. A prose test based on line length alone
accepts them, so the plate's top edge lands in the middle of its own labels.
**Fix.** Three tests, all required: **≥12 CJK characters** (a tick row has
none, a table row has one or two), **runs ≥50 % of the column**, and **starts at
the page's body margin** (the modal `x0` of wide lines). The CJK count is the
one that separates a paragraph from the table grid underneath a 表N.M caption —
both start at the margin and run the full column, so geometry alone cannot.

### H15. ★ OCR glues the caption label to its title, and the number parses wrong
**Cause.** `图1.13　1美元兑人民币汇率` arrives as `图1.131美元兑人民币汇率` and
parses as **figure 1.131**. Every later number in the chapter shifts.
**Fix.** Assign figure numbers by **sequence within the chapter**, not by
trusting the split. A candidate whose leftover text starts with a digit
(`008年…`) cannot be a title; `2008年…` can. A continuation caption
(`图1.6…（续）`) **repeats** the previous number rather than advancing — counting
it as new pushes everything after it up by one.

### H16. ★ A running header gets swallowed by any plate that fills the page top
**Cause.** When a figure occupies the upper half of a page there is no prose
above it, so the nearest-prose search returns the page margin and the crop
starts at the very top — including `缠斗：中美经贸重构与全球经济新秩序`.
Geometry cannot distinguish "plate" from "plate plus header".
**Fix.** Bound the crop's upper edge by the **header's own bottom**, computed as
the last row inside the top ~8 % of the page. And **look at three or four
crops**: this one was invisible in every number and obvious in the images.

---

## I. Gates that report success for work they never did

### I1. ★★★ The probe crashed and the gate called it a pass
**Cause.** The reader probe had another book's section id hard-coded. It threw
on the first assertion, `--dump-dom` returned no report, `readercheck.py`
crashed, and `check_all.py` did this:

```python
for line in rc.splitlines():          # rc is a traceback: zero matching lines
    if line.startswith("  !!"): check(False, ...)
    elif line.startswith("  --"): check(True, ...)   # body never runs
```

Every check that was never executed was reported as passing, and the run printed
**"all checks passed"**.
**Fix.** Require a positive signal, never the absence of a negative one:
```python
m = re.search(r"(\d+)/(\d+) reader-control checks passed", rc)
check(m is not None, "probe produced a verdict list (%d bytes)" % len(rc))
if m: check(m.group(1) == m.group(2) and int(m.group(2)) >= 20, ...)
```
Generalised: **a stage must assert that it produced output, and how much.**

### I2. ★★ A checker that can only fail is as useless as one that can only pass
**Cause.** `check_captions.py` reported **all 83** captions as wrong. The checker
was broken twice: it matched only `图N.M` (this book labels tables `表N.M`), and
it compared the whole caption including the reader-facing suffix
`· 点击可放大`.
**Fix.** When failure is 100 % across unrelated content, suspect the checker.
Print the first mismatched pair and read it before touching the content.

### I3. ★ Measuring an element that cannot carry the property
**Cause.** The night-mode assertion read `querySelector("svg.chart [fill]")` and
required the colour to change. The first match is a line path with
`fill="none"` — not a colour, never remapped — so a correct implementation
failed.
**Fix.** Walk until you find a node whose attribute is actually a hex colour.
Same family as D4/D7: the measurement was fine, the subject was wrong.

### I4. ★ A reused probe silently tests the previous book
**Cause.** The inherited probe hard-coded that book's section id (`c12`), TOC
label (`第12章`), search term (`毕生发展观`), storage prefix (`hbj:`) and palette.
Even if it had not crashed, it would have been testing the wrong contract.
**Fix.** Generate a fresh probe per book and derive ids from the document at
runtime: `scripts/make_reader_probe.py --term 关税 --latin gdp --storage cd:`.

### I5. ★ Two Chrome processes sharing one profile render a blank page
**Cause.** Screenshots shared `--user-data-dir`. A lingering Chrome from the
previous shot held the profile lock, so the next one produced a 9 kB
paper-coloured PNG — which reads as "the page is blank", not "the capture
failed".
**Fix.** One profile directory per capture, removed afterwards. And treat an
implausibly small screenshot (< 50 kB for a full page) as a failure, not a
result.

### I6. ★★★ A fix applied to generated output is silently reverted by the next build
**Cause.** The gate flagged eight low-contrast labels. I fixed them by editing
`frag/*.html` — the files the assembler reads — and the gate went green. Much
later, a routine `expand.py` run regenerated those fragments **from `frag/*.src`**
and every fix vanished. The same thing happened to a note-numbering repair:
`notechk` went from 0 problems to 5 the moment the fragments were re-expanded.

Nothing warned. The `.html` is not the source; it is a build artifact with the
same extension as the hand-written files, which is exactly why the mistake is
easy.

**Fix, in two parts.**
1. **Know which files are generated.** `expand.py` prints
   `hand-written (no .src, left untouched): c04 guide hero` — anything *not* in
   that list is generated and must never be edited.
2. **Make the build prove it.** After editing, re-expand and re-audit. If a fix
   survives `expand.py` + `assemble.py`, it is in the source; if the gate goes
   red again, it was in the output.

A useful habit: any repair script should open `frag/<CID>.src`, never
`frag/<CID>.html`. If a fix cannot be expressed in the `.src`, the shortcut
layer is missing a case — add one.

### I7. ★ Deleting "scratch" can delete the input
**Cause.** A cleanup pass that removed audit artifacts by wildcard also removed
the source PDF from the project root. It was recoverable from the Recycle Bin,
but the next script run failed with a mojibake `FileNotFoundError` that looked
like an encoding bug — the CJK filename had been mangled *because the file was
not there*.
**Fix.** Never wildcard-delete at the project root. Clean inside the build
directory (`_audit/`, `cprof/`, `*.dump`), and confirm the input still exists
before blaming encoding for a missing-file error.

---

## The meta-lesson

**Build the measurement first.** D6 is the clearest case: the audit tool was
wrong in a way that produced a confident zero, and the "fix" it prompted made
the page worse. Every false-zero above was found only by cross-checking a
second way — counting independently, opening the actual source, toggling the
palette and re-measuring, or simply *running the extractor against a real
file* instead of trusting that it should work. If a check can only ever pass,
it isn't a check.

The 《缠斗》 run added the mirror image: **a gate can also report success for work
it never did** (I1). An empty result set, a crashed sub-process, a probe aimed at
the wrong book — all of them produce the same green summary. The defence is the
same in both directions: assert a *count*, and make zero a failure.
# Audit gates — and the ways a gate lies

Companion to `auditing.md`. That file explains *what* to measure. This one is
about the gate itself: the eight stages, the order to run them in, and the
failure modes where a gate reports success for work it never did.

---

## The eight stages

| # | Stage | Script | Fails when |
|---|---|---|---|
| 1 | structure of the built file | `assemble.py` tail | tag imbalance, duplicate SVG ids, stray fences, broken anchors |
| 2 | fragment metrics | `validate.py` | any fragment below its tier floors |
| 3 | note linkage | `notechk.py` | marker without item, item without marker, duplicate id, non-contiguous numbering |
| 4 | caption traceability | `check_captions.py` | a caption that isn't in `figs.json`, or describes the picture |
| 5 | chart legibility, light | `runaudit.py` × 4 widths | overflow / tiny / overlap / out-of-box / covered / low-contrast |
| 6 | card & block layout | `runaudit2.py` × 4 widths | clipped, cramped, blank, ragged, gaps, touching, orphan |
| 7 | chart legibility, dark | `runaudit.py --dark` × 4 | same counters, dark palette |
| 8 | reader controls | `readercheck.py` | TOC / search / theme / position / lightbox |

Exit 0 only if all eight pass. **Always rebuild first** — stages 5–8 read the
built file.

---

## How a gate lies

Every one of these happened in a real run.

### L1 — iterating over an empty result set

```python
rc = run("readercheck.py")
for line in rc.splitlines():
    if line.startswith("  !!"): check(False, ...)
    elif line.startswith("  --"): check(True, ...)
```

The probe crashed (it had hard-coded another book's section id), printed a
traceback, and emitted no verdict lines. The loop body never ran. **Every check
that was never executed was reported as passing**, and the run printed
"all checks passed".

The fix is to require a positive signal, not just the absence of a negative one:

```python
m = re.search(r"(\d+)/(\d+) reader-control checks passed", rc)
check(m is not None, "probe produced a verdict list")
if m:
    check(m.group(1) == m.group(2) and int(m.group(2)) >= 20, ...)
```

Generalised: **a stage must assert that it produced output**, and how much. A
stage whose success condition is "nothing went wrong" cannot fail.

### L2 — a check that can only fail

`check_captions.py` first reported all 83 captions as wrong. The checker was
broken twice over: it matched only `图N.M` (this book labels tables `表N.M`), and
it compared the whole caption including the reader-facing suffix
`· 点击可放大`.

Symptom to recognise: **100% failure across unrelated content**. If everything
is wrong, suspect the checker before the content. Print the first mismatched
pair and read it.

### L3 — measuring the wrong element

The night-mode probe read `document.querySelector("svg.chart [fill]")` and
asserted the colour changed. The first match is a line path with
`fill="none"` — not a colour, never remapped — so the assertion failed on a
correct implementation. Walk until you find a node that actually carries a hex
value.

Same family as D4/D7 in `auditing.md`: the measurement was fine, the *subject*
was wrong.

### L4 — a fix that satisfies the audit and breaks the page

Documented at length as D6: the contrast audit ignored `fill-opacity`, reported
1.0:1 against a pale wash, and the "fix" turned label text white on cream.
**Before acting on a finding, open the source it is complaining about.** If the
audit and your eyes disagree, the audit is more likely wrong than your eyes —
but both need checking.

### L5 — the report exists but describes a stale build

`check_all.py` calls `assemble.py` in stage 1, but `runaudit.py` reads
`../<book>.html`. If a previous stage crashed after assembly, stages 5–8 measure
the *old* file. Print the deliverable's size and mtime in stage 1 and eyeball it.

### L6 — a green gate that measured a reverted fix

The gate went red, the fix was applied to `frag/*.html`, the gate went green.
Later a routine `expand.py` regenerated those fragments from `frag/*.src` and
the fix disappeared — the gate would have caught it, but only if it ran again
*after* the rebuild. It did, and it did.

The lesson is about **the order of operations**, not the gate: the gate only
ever validates the current build. A fix that is not in the source is not a fix,
it is a state that happens to pass.

**Rule.** After any repair: `expand.py` → `assemble.py` → `check_all.py`, in
that order, every time. If the third step goes red again, the repair landed in
the wrong file.

---

## Determinism, every run

Chrome persists `localStorage` in `--user-data-dir`, so a `--dark` run leaks
into the next light run and the numbers describe the wrong palette (D11). Pin
both directions on **every** launch:

```html
<style>*,*::before,*::after{transition:none!important;animation:none!important}
html{scroll-behavior:auto!important}</style>
<script>try{localStorage.removeItem("<prefix>pos");
localStorage.setItem("<prefix>theme",JSON.stringify("light"));}catch(e){}</script>
```

Also give each screenshot or probe run **its own profile directory**. Two
concurrent Chrome processes sharing one profile silently render a blank page;
this cost several rounds of debugging a "blank screenshot" that was actually a
profile lock.

---

## Screenshots are not the audit

The gate is geometry. Screenshots are for *you* — to catch what geometry cannot
express: a chart whose labels are technically legible but semantically
misplaced, a crop that includes the page header, a section that reads badly.

When you do take them:

- **A single capture taller than ~16 000 px silently stops painting.** Slice the
  document (one section per capture) rather than scrolling a 160 000 px page.
- **A URL fragment (`file.html#c01`) returned a blank paper-coloured image** in
  this run. Extracting the section into its own small page worked reliably.
- Force `.reveal` visible before capturing, or you photograph `opacity:0`:
  ```html
  <style>.reveal{opacity:1!important;transform:none!important}
  .chart .pop{opacity:1!important}
  .chart .draw{stroke-dashoffset:0!important}
  .chart .grow,.chart .growx{transform:none!important}</style>
  ```

---

## Order of work when something fails

1. **Read the failing stage's own output**, not the summary line.
2. **Reproduce that one stage** at one width. The full gate is 16 Chrome
   launches; iterating on it is slow.
3. **Look at the source** the stage points at.
4. Fix the *source* (`frag/*.src` or `.html`, `style.css`, `app.js`), never the
   built file.
5. Re-run the single stage, then the whole gate.
6. Re-run the whole gate once more after cleanup — cleanup has broken a build
   before.

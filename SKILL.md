---
name: book-to-interactive-html
description: Turn any book — EPUB, PDF (digital or scanned), DOCX, HTML, or loose text+images — into ONE self-contained, richly-illustrated interactive HTML book with per-chapter explanation, hand-built animated SVG charts, click-to-zoom images, endnotes, table of contents, full-text search, night mode and saved reading position, all proven by a headless-Chrome geometry audit instead of eyeballing screenshots. Use when the user says 把书/pdf/epub/电子书 转成 HTML, "详解图", "做成一个网页书", "一整个 HTML 文件", 逐章讲解, 精读, 图解版, "保留图片和注释", 图表动效, 夜间阅读模式, 目录搜索, 记住阅读位置, book to html, pdf to interactive html, interactive book, or asks to rebuild or fix an existing book conversion. Triggers include "epub to html", "pdf to html", "book to html", "详解图", "网页书", "图解", "interactive book", "章节动画", "扫描版 pdf", "扫描件", "OCR 一本书", "做成可以续读的网页", "书籍转网页".
---

# book-to-interactive-html — 任意电子书 → 单文件交互式 HTML 书

Convert a book into **one** `.html` file that opens offline, keeps every
knowledge point, and is verified by measurement rather than by looking.

Source format is a stage-2 concern only. EPUB, PDF (digital or scanned),
DOCX and HTML all converge on the same `pack/<CID>.md` + `frag/<CID>.html`
before anything else happens.

## The one rule that makes this work

> **Never hand-edit the built HTML. Edit `frag/*.html`, `style.css` or
> `app.js`, then rebuild with `assemble.py`.**

The output is a 14 MB generated artifact. Editing it directly means the next
build silently discards your work, and you cannot diff what changed. All
content lives in small editable fragments; the assembler owns the glue.

## Build layout

```
<book>-build/
  frag/<CID>.src   ← authoring source for GENERATED fragments (prose + SVG +
                     {{FIG:...}} shortcuts). Expand with scripts/expand.py.
  frag/<CID>.html  ← the fragment the assembler reads. Generated from .src when
                     a .src exists; hand-written otherwise (the guide usually is).
  pack/<CID>.md    ← chapter text + fact pack. The ONLY source of numbers,
                     dates and names. Never write a fact that isn't here.
  style.css        ← design system: :root tokens, components, responsive, print
  app.js           ← reader runtime: TOC, search, theme, position, lightbox
  assemble.py      ← concatenates fragments + inlines CSS/JS/images → ONE file
  raw/ text/       ← extraction output (raw/ocr/, raw/lines.json, raw/paragraphs.txt)
  figs.json        ← plate record: filename → printed caption, page, crop box
  imgb64.json      ← base64 image cache
  sections.py      ← section ids, titles, accents, which plates each owns
  validate.py      ← per-fragment quota gate
  check_all.py     ← the gate. Must exit 0.
../<book>详解图.html   ← THE DELIVERABLE
```

**Never edit a generated `frag/*.html`** — edit its `.src` and re-expand, or the
next expansion discards the edit. Same rule as the deliverable itself.

## Scripts

| Script | What it does |
|---|---|
| `scripts/ocr_lines.py` | scanned PDF → per-page OCR cache → `lines.json` (with geometry) → **rebuilt paragraphs**. Paragraphs matter: a line list makes an unusable fact pack (H12). |
| `scripts/crop_plates.py` | scanned PDF → `fig/*.jpg` + `figs.json`, locating plates by caption + prose boundary + measured ink (H13–H16). |
| `scripts/expand.py` | `frag/*.src` → `frag/*.html`; turns `{{FIG:fig01_01}}`, `{{QUIZ:...}}`, `{{NOTES:...}}` into real markup. |
| `scripts/check_captions.py` | every caption quotes one the book printed, and none describes the picture. |
| `scripts/make_reader_probe.py` | generates a reader-controls probe for *this* book (I1, I4). |
| `scripts/chrome_probe.py` | runs any JS probe in headless Chrome, returns its JSON. |
| `scripts/extract_*.py` | EPUB / PDF / DOCX extraction. |
| `scripts/validate_skill.py` | checks this file's frontmatter parses (G3, G4). |

## Pipeline

### 1. Identify the format, then extract

`references/source-formats.md` has the decision table and the per-format
detail. **For a scanned PDF, read `references/scanned-book-walkthrough.md`** —
it is the whole sequence with the numbers a healthy run produces.

```bash
python scripts/extract_epub.py book.epub -o epub-build
python scripts/extract_pdf.py  book.pdf  --toc        # outline present?
python scripts/extract_docx.py book.docx -o docx-build

# scanned PDF — start this FIRST, it dominates machine time
python scripts/ocr_lines.py  book.pdf -o <book>-build --workers 10
python scripts/crop_plates.py book.pdf -o <book>-build
```

**Print the spine/outline and look at it before writing anything.** Many books
have dozens of entries, most of them covers and copyright pages. For a scanned
PDF there is no outline at all and you must derive the chapter page ranges
yourself — see the format reference.

### 2. Build the fact pack
One `pack/<CID>.md` per chapter: the source text plus every number, date,
name and quotation. This is what makes "no knowledge points lost" auditable —
later, `check_captions.py` verifies every caption traces back into it.

**The pack must be prose, not a line list.** A pack built from raw OCR lines
cuts every sentence at the printed line width, and a writer reading it cannot
tell a paragraph break from a line wrap (H12). `ocr_lines.py --paragraphs`
rebuilds paragraphs from line geometry — use it.

Give each pack these sections, in this order:

```markdown
# 第一章　标题
- 物理页（PDF 1-based）：39–130       ← for get_pixmap()
- 原书印刷页：21–112                  ← for citations
- 段落数 / 含数字的句子 / 页脚注释

## 本章图表（原书）      filename + verbatim caption + printed page
## 含数字的句子           [pNN] sentence  — the writer's index
## 页脚注释（原书原文）    [pNN] note text — copied verbatim, never abridged
## 正文（按原书页序）      【原书 pNN】 + paragraphs
```

### 3. Decide the contract BEFORE writing prose
Write into `SPEC.md`: section ids and order, per-chapter accent colour, which
original chapters are dropped (e.g. 参考文献) and which notes survive, and the
content totals you will diff later. Everything downstream references it.

`references/splitting-and-delegation.md` has the cut/drop/merge decision table
and the fragment quota tiers.

### 4. Write fragments
One fragment per section. Each starts with:

```html
<section class="chapter" id="ch07" style="--accent:#6E7B2E">
```

Content classes: `.card` (+ `.card bad` for misconceptions — the highest-value
card), `.step`, `.quote`, `.formula`, `.quiz`, `.case`, `.stat`/`.stats`,
`.numline` (chapter-opening headline numbers), `.tbl`, `.cmp`, `.fig`,
`.chart` + `.chart-cap`, `sup.nb` + `details.notes`. Editorial additions get
`class="ed"`.

Endnote linkage is `<sup class="nb" data-n="ch07-n3">3</sup>` ↔
`<li id="ch07-n3">`, one-to-one, numbered 1..N with no gaps and no duplicates.

> **Author `.src`, not `.html`.** The repetitive parts — 36 `<figure>` blocks,
> the notes list, the quiz, the pager — become one line each via
> `scripts/expand.py`, so only prose and hand-drawn SVG are typed. That removes
> transcription errors in caption text, which is the one thing the checker
> compares verbatim. See `references/splitting-and-delegation.md`.

> Delegating chapters to subagents works, but **~25% of dispatches produce no
> file at all** — verify each output exists and grew before trusting it. Give
> each writer the pack path (never paraphrased facts), an exact output path, an
> exact quota checklist, and the validator command to iterate on. See pitfalls
> B1–B4 and `references/splitting-and-delegation.md`.

### 5. Author SVG charts
Hand-built SVG, one `<svg class="chart">` per figure. Rules and reasons in
`references/charts.md`. Short version — `viewBox` width fixed at 900, no
`<rect>` (jittered `<path>` instead), all text after all shapes, minimum 12-unit
labels, one chart per row, annotation callouts over legends.

### 6. Assemble
`python assemble.py` → the single file. It inlines `style.css`, `app.js` and
every image as a base64 data URI, injects the topbar/panels, and prints
structural counts (svg/details/table/figure balance, duplicate def ids).

### 7. Reader features
TOC, full-text search, night mode, saved reading position, click-to-zoom
lightbox. Working implementation in `assets/reader.css` + `assets/reader.js`;
the bug each one shipped with in `references/reader-features.md`.

### 8. Audit — mandatory
`python check_all.py` rebuilds and runs eight gates; it must exit 0.
A book is mostly layout, so the only trustworthy check is **real geometry
measured in a headless browser**. See `references/auditing.md`,
`references/gate-design.md` and `scripts/chrome_probe.py`.

Generate a fresh reader probe for every book — a reused one tests the previous
book's ids and may crash into a false pass:

```bash
python scripts/make_reader_probe.py --term 关税 --latin gdp --storage cd:
```

## Hard rules

- **Never hand-edit the deliverable, or a generated fragment.** Edit
  `frag/*.src`, `style.css` or `app.js`, then rebuild/re-expand. `expand.py`
  prints which fragments are hand-written; everything else is generated, and a
  fix applied to it is silently reverted by the next build (I6).
- **Never state a fact that is not in `pack/<CID>.md`.** No invented page
  numbers, no fabricated quotations. Attribute the author's opinions as the
  author's view. For scanned sources, verify every number against the page
  image — OCR gets digits wrong.
- **Never claim content is preserved without counting.** Re-grep the built
  file for note markers, images, charts, tables and sections and diff against
  the numbers you recorded in stage 3.
- **Never trust a contrast or layout judgement you eyeballed.** Measure it.
- **A check that produced no output is a failure, not a pass.** Every gate
  stage must assert that it emitted a verdict — an empty result set silently
  green-lights work that never ran (I1).
- **Always rebuild before auditing** — audits read the built file.
- **Never wildcard-delete at the project root.** Clean inside `_audit/` and the
  profile dirs only; a cleanup pass has deleted the source PDF (I7).
- Clean scratch (`*.html`, `*.dump`, `*.report.json`, profile dirs) before
  delivery, but keep the audit scripts: they are the requested inspection step.

## Traps

Read `references/pitfalls.md` before starting and whenever something looks
wrong. It records every failure from building real books — regex backtracking
that silently matched nothing, audits that reported both false zeros and true
zeros, a "fix" that made a page less readable, and more.

Groups, in the order they tend to bite:

| Group | Domain |
|---|---|
| A–C | extraction plumbing, subagents, assembly |
| D–F | headless-Chrome auditing, reader features, dark mode |
| G | content integrity |
| H | PDF / OCR sources — **H12–H16 are the scanned-book traps** |
| I | gates that report success for work they never did — **I6 is "a fix to generated output gets reverted"** |

The single most expensive trap across two books is **I6**: fixing the built
fragment instead of the `.src`, then losing the fix at the next build. If you
remember one thing from this file, remember which files are generated.

## What "done" looks like

A 23万字 EPUB produced **one 13.8 MB HTML file**: 15 sections, 13 chapters of
explanation, 83 hand-built animated SVG charts, 46 figures with 47 inlined
images, 289 endnotes, 18 tables, plus TOC / full-text search / night mode /
saved reading position. `check_all.py` exits 0 at widths 1440, 1024, 768 and
430 — in both light and night mode — with every geometry counter at zero.

A 418-page **scanned** Chinese PDF (zero text layer, no outline) produced
**one 7.45 MB HTML file**: 9 sections, **83 plates cropped from the scan**, 35
hand-built charts, **172 endnotes**, 77 cards, 28 case boxes, 19 stat blocks.
The gate exited 0 at four widths × two palettes with 32/32 reader checks. The
full run is written up in `references/scanned-book-walkthrough.md`.

If a number in your own run looks materially worse than these, something in the
pipeline is quietly dropping content — find it before shipping.
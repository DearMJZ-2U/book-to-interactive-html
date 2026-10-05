---
name: book-to-interactive-html
description: Turn any book — EPUB, PDF (digital or scanned), DOCX, HTML, or loose text+images — into ONE self-contained, richly-illustrated interactive HTML book with per-chapter explanation, hand-built animated SVG charts, click-to-zoom images, endnotes, table of contents, full-text search, night mode and saved reading position, all proven by a headless-Chrome geometry audit instead of eyeballing screenshots. Use when the user says 把书/pdf/epub/电子书 转成 HTML, "详解图", "做成一个网页书", "一整个 HTML 文件", 逐章讲解, 精读, 图解版, "保留图片和注释", 图表动效, 夜间阅读模式, 目录搜索, 记住阅读位置, book to html, pdf to interactive html, interactive book, or asks to rebuild or fix an existing book conversion. Triggers include "epub to html", "pdf to html", "book to html", "详解图", "网页书", "图解", "interactive book", "章节动画", "扫描版 pdf".
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
  frag/            ← THE EDITABLE SOURCE. One .html per chapter + _guide.html
  pack/<CID>.md    ← chapter text + fact pack. The ONLY source of numbers,
                     dates and names. Never write a fact that isn't here.
  style.css        ← design system: :root tokens, components, responsive, print
  app.js           ← reader runtime: TOC, search, theme, position, lightbox
  assemble.py      ← concatenates fragments + inlines CSS/JS/images → ONE file
  raw/ text/       ← extraction output
  imgb64.json      ← base64 image cache
  check_all.py     ← the gate. Must exit 0.
../<book>详解图.html   ← THE DELIVERABLE
```

## Pipeline

### 1. Identify the format, then extract

`references/source-formats.md` has the decision table and the per-format
detail. One command each:

```bash
python scripts/extract_epub.py book.epub -o epub-build
python scripts/extract_pdf.py  book.pdf  --toc        # outline present?
python scripts/extract_pdf.py  book.pdf  --ocr --pages 1-100   # scanned
python scripts/extract_docx.py book.docx -o docx-build
```

**Print the spine/outline and look at it before writing anything.** Many books
have dozens of entries, most of them covers and copyright pages. For a scanned
PDF there is no outline at all and you must derive the chapter page ranges
yourself — see the format reference.

### 2. Build the fact pack
One `pack/<CID>.md` per chapter: the source text plus every number, date,
name and quotation. This is what makes "no knowledge points lost" auditable —
later, `capcheck.py` verifies every caption traces back into it. OCR text is
noisy; clean it here, before writing any prose.

### 3. Decide the contract BEFORE writing prose
Write into `SPEC.md`: section ids and order, per-chapter accent colour, which
original chapters are dropped (e.g. 参考文献) and which notes survive, and the
content totals you will diff later. Everything downstream references it.

### 4. Write fragments
One `frag/<CID>.html` per section. Each starts with:

```html
<section class="chapter" id="ch07" style="--accent:#6E7B2E">
```

Content classes: `.card`, `.step`, `.quote`, `.formula`, `.quiz`, `.case`,
`.stat`, `.tbl`, `.fig`/`.figpair`, `.chart-cap`, `sup.nb` + `details.notes`.
Endnote linkage is `<sup class="nb" data-n="ch07-n3">3</sup>` ↔
`<li id="ch07-n3">`. Editorial additions get `class="ed"`.

> Delegate chapters to subagents when there are many. Give each one the fact
> pack and an exact output file; tell it not to touch `style.css` or other
> fragments. See pitfalls B1–B4.

### 5. Author SVG charts
Hand-built SVG, one `<svg class="chart">` per figure. Rules and reasons in
`references/charts.md`. Short version — `viewBox` width fixed at 900, no
`<rect>`, all text after all shapes, minimum 12-unit labels, one chart per row.

### 6. Assemble
`python assemble.py` → the single file. It inlines `style.css`, `app.js` and
every image as a base64 data URI, injects the topbar/panels, and prints
structural counts (svg/details/table/figure balance, duplicate def ids).

### 7. Reader features
TOC, full-text search, night mode, saved reading position. Working
implementation in `assets/reader.css` + `assets/reader.js`; the bug each one
shipped with in `references/reader-features.md`.

### 8. Audit — mandatory
`python check_all.py` rebuilds and runs eight gates; it must exit 0.
A book is mostly layout, so the only trustworthy check is **real geometry
measured in a headless browser**. See `references/auditing.md` and
`scripts/chrome_probe.py`.

## Hard rules

- **Never hand-edit the deliverable.** Only fragments/CSS/JS, then rebuild.
- **Never state a fact that is not in `pack/<CID>.md`.** No invented page
  numbers, no fabricated quotations. Attribute the author's opinions as the
  author's view. For scanned sources, verify every number against the page
  image — OCR gets digits wrong.
- **Never claim content is preserved without counting.** Re-grep the built
  file for note markers, images, charts, tables and sections and diff against
  the numbers you recorded in stage 3.
- **Never trust a contrast or layout judgement you eyeballed.** Measure it.
- **Always rebuild before auditing** — audits read the built file.
- Clean scratch (`*.html`, `*.dump`, `*.report.json`, profile dirs) before
  delivery, but keep the audit scripts: they are the requested inspection step.

## Traps

Read `references/pitfalls.md` before starting and whenever something looks
wrong. It records every failure from building real books — regex backtracking
that silently matched nothing, audits that reported both false zeros and true
zeros, a "fix" that made a page less readable, and more. Group H is specific
to PDF/OCR sources.

## What "done" looks like

A finished run of this pipeline on a 23万字 EPUB produced **one 13.8 MB HTML
file** containing: 15 sections, 13 chapters of explanation, 83 hand-built
animated SVG charts, 46 figures with 47 inlined images, 289 endnotes, 18
tables, plus TOC / full-text search / night mode / saved reading position.
`check_all.py` exits 0 at widths 1440, 1024, 768 and 430 — in both light and
night mode — with every geometry counter at zero.

That build's `check_all.py`, `audit.js`, `runaudit.py` and `readerprobe.js`
are real implementations of the gate in `references/auditing.md`; the scanned
PDF path (OCR + hand-derived page ranges) has been exercised on 489-page and
441-page books.

If a number in your own run looks materially worse than the above, something
in the pipeline is quietly dropping content — find it before shipping.
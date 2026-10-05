# Source formats

Every input format converges on the same two things, and **nothing after
stage 2 knows where the book came from**:

1. `pack/<CID>.md` — the chapter text plus every fact (numbers, dates, names)
2. `frag/<CID>.html` — your authored fragment

So format extraction is a *separate, swappable* concern. Pick the extractor,
get `meta.json`, decide the chapter split, and never think about it again.

## Which format is this?

| Input | Extractor | Chapter boundaries | Figures |
|---|---|---|---|
| `.epub` | `extract_epub.py` | automatic — the spine **is** the chapter list | embedded images, clean |
| `.pdf` (digital text layer) | `extract_pdf.py` | outline if present, else derive from page text | `--images` pulls embedded rasters |
| `.pdf` (scanned images) | `extract_pdf.py --ocr` | **you must derive them** — no outline exists | `--images` often empty; crop from page renders |
| `.docx` | `extract_docx.py` | automatic — Heading 1 outline | relationships, clean |
| `.html` / `.txt` | trivial: strip to text, split yourself | headings | whatever is referenced |

Already have text + images separately? Skip extraction — write the packs by
hand and go straight to stage 3.

---

## EPUB

The friendliest input. `zipfile` → `content.opf` → spine gives you the true
reading order. **`toc.ncx` is advisory; the spine is authoritative** — some
books have a toc that disagrees with the actual order.

```bash
python scripts/extract_epub.py book.epub -o epub-build
```

Print the spine and **look at it before writing anything**. Many epubs have
dozens of spine entries, most of them 5–100 characters: covers, copyright
pages, nav documents. Decide what is a chapter and what is dropped, and write
that into `SPEC.md`.

## PDF — digital

```bash
python scripts/extract_pdf.py book.pdf --toc          # is there an outline?
python scripts/extract_pdf.py book.pdf -o pdf-build --images
```

PyMuPDF (`fitz`) reads the text layer directly. Fast, accurate.

## PDF — scanned

The script detects this: if the first 12 pages yield under 200 characters it
refuses to continue without `--ocr`. Do not skip that check — **a scanned
book without OCR produces empty chapters that look like a successful run**
(pitfall H1).

```bash
python scripts/extract_pdf.py book.pdf --ocr -o pdf-build --pages 1-40
```

RapidOCR at 200 dpi is roughly 1–4 s per page. Run it **in batches with
`--pages`, resumable** — per-page JSON is cached, so a crash costs one batch:

```
python scripts/extract_pdf.py book.pdf --ocr --pages 1-100
python scripts/extract_pdf.py book.pdf --ocr --pages 101-200
```

OCR returns boxes, not a string. Reading order is reconstructed by sorting on
`(round(y/12), x)` — tune the bucket size if columns come out interleaved.

### The PDF-specific trap: no table of contents

A scanned book has no machine-readable chapter list. You must build one.
Sample every ~10 pages, find the chapter headings, and record the ranges
yourself:

```python
PARTS = [
    ('ch01', '第一章　什么是文化？',  43,  74),
    ('ch02', '第二章　如何了解文化？', 75, 110),
    ('end',  '结语',               455, 461),
    ('biblio','参考书目',          473, 489),   # usually dropped
]
```

Record **physical** page numbers (1-based, what `page.get_text()` takes), not
the printed page number. They differ by the front matter, and every later
"page N" reference is off if you confuse them (pitfall H3).

### Figures in scanned PDFs

`--images` will often find nothing — a scan is one big raster per page. Crop
regions from a page render instead:

```python
pix = doc[pno].get_pixmap(dpi=200)          # whole page
clip = fitz.Rect(x0, y0, x1, y1)            # fractions of the page
doc[pno].get_pixmap(dpi=200, clip=clip).save("fig/ch05_01.png")
```

The OCR boxes double as the crop hints — a caption box tells you the figure
is directly above it.

---

## DOCX

`extract_docx.py`. Chapters come from Heading 1 in document order. Walks the
body XML **once**, so paragraphs and tables interleave correctly instead of
being read in two separate passes (pitfall H8). Heading detection matches the
`w:outlineLvl` property — on the paragraph *or* on its style — rather than the
localised style name, so it works on a Chinese Word install where the style is
`标题 1` (pitfall H9).

---

## From here it is identical

Whichever extractor ran, you now need the same three things:

1. **A chapter list with ids and titles** — write `ORDER` in `assemble.py`.
2. **A fact pack per chapter** — `pack/<CID>.md`. This is the only legal
   source of numbers, dates, names and quotations. If the source format made
   the text hard to read (OCR noise, column bleed), fix it here: clean the
   text before writing any prose.
3. **Content totals to preserve** — write them down now
   (`notes: 289, images: 47, tables: 18`) and diff them after every build.
   This is your only evidence that nothing was lost.

## Quality bar per format

OCR text is *worse* than EPUB text, so compensate:

- **Scanned PDF** — expect character errors in names and numbers. Never take a
  number from OCR without checking it against the rendered page image. Budget
  more time for the fact pack than for the prose.
- **Digital PDF** — watch for hyphenation and ligatures across line breaks
  (`inter-\nnational`), and for headers/footers repeating into the text.
  Strip page furniture before packing.
- **EPUB** — usually clean; watch for `display:none` furniture (page numbers,
  nav) that survives naive tag stripping.
- **All** — drop the bibliography, keep every annotation, unless told
  otherwise. Record the decision in `SPEC.md`.
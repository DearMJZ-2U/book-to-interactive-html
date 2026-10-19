# Scanned-PDF book — the full walkthrough

A 418-page scan of 《缠斗：中美经贸重构与全球经济新秩序》 (Chinese, 2026, five
chapters) went from a 67 MB image-only PDF to a 7.45 MB single-file HTML book in
one session. This is that run, in order, with the numbers each step produced so
you can tell whether your own run is on track.

Read this before starting a scanned book. The other references explain *why*;
this one is the sequence.

---

## 0. Budget

| Stage | Time | Notes |
|---|---|---|
| OCR 418 pages @200 dpi, 10 workers | **~45 min** | ~4.5 s/page wall-clock |
| Line/paragraph reconstruction | seconds | |
| Plate cropping + review | ~10 min | review is the slow part |
| Fact packs | seconds | |
| Writing 9 fragments (delegated or solo) | the bulk | |
| Audit loop | ~15 min per full pass | 16 Chrome launches |

OCR dominates the machine time and is fully parallel. **Start it first, before
writing a single line of anything else.**

---

## 1. Confirm it really is a scan

```python
import fitz
d = fitz.open(pdf)
print(d.page_count, d.get_toc(), d.metadata)
for i in range(10):
    print(i, len(d[i].get_text()), len(d[i].get_images()))
```

The 《缠斗》 PDF returned `0 chars` on every page, `get_toc() == []`, and one
image per page — a RICOH scanner (`creator: RICOH Aficio MP 7502`, `producer:
iLovePDF`). That combination means: no text layer, no outline, and every plate
is a rectangle inside a page raster.

**`get_toc() == []` is information, not an error** (pitfall H2). You will derive
the chapter map yourself.

---

## 2. OCR — start it in the background, now

```bash
python scripts/ocr_lines.py book.pdf -o <book>-build --workers 10
```

It caches one JSON per page under `raw/ocr/`, so it is resumable and a crash
costs one page. While it runs, do steps 3–5 on whatever pages are already done.

Two settings matter:

- **10 workers, 1 thread each.** RapidOCR already saturates a core; N processes
  × N threads thrashes. Measured: 1 worker = 3.3 s/page, 10 workers = 4.5 s/page
  wall-clock (≈22× throughput).
- **200 dpi.** 300 dpi produced *identical* text on a spot check and cost 8%
  more. 200 is enough for 10 pt CJK.

Never feed it `pix.tobytes("png")` — that is a 1-D array and RapidOCR rejects it
(pitfall H7). Raw samples only.

---

## 3. Derive the chapter map (no outline exists)

Three independent signals, cross-checked:

| Signal | What it gives |
|---|---|
| 目录 (contents) pages | chapter titles + **printed** start pages |
| Running header `第N章<title>` | where each chapter actually begins |
| Bare folio at the foot | printed ↔ physical page offset |

The offset is a **majority vote**, never an assumption. 《缠斗》 came out at
**18**, from 410 pages that carried a folio.

```
folio pages: 410 / 418
offset candidates: [(18, 182), (-51, 1), (-543, 1)]
offset (mode): 18
ch1 phys p39   printed p21   headers=45
ch2 phys p131  printed p113  headers=38
ch3 phys p209  printed p191  headers=28
ch4 phys p269  printed p251  headers=49
ch5 phys p367  printed p349  headers=24
```

Every chapter's printed page was then **checked** against the offset rather than
trusted — a chapter whose headers disagree is flagged, not silently
mis-paginated (pitfall H3).

Record both numbers in `SPEC.md`. Every citation downstream uses the printed
page; every `get_pixmap()` call uses the physical one.

---

## 4. Rebuild paragraphs — this is the step people skip

`ocr_lines.py --paragraphs` writes `raw/lines.json` (each line keeps `x0`/`x1`)
and `raw/paragraphs.txt`.

**Build the fact packs from `paragraphs.txt`, not from a line list.** A pack of
shredded lines is unusable:

```
（世界发展指标）数据库的统计，2008年东亚及太平洋地区（含东
南亚）的制造业增加值约占全球的33.94%，中国当时的全球占比
为11.3%；2024年，该地区这一比重增加到42.58%，中国的全球
```

versus the same text rebuilt:

```
根据世界银行WDI（世界发展指标）数据库的统计，2008年东亚及太平洋地区
（含东南亚）的制造业增加值约占全球的33.94%，中国当时的全球占比为11.3%；
2024年，该地区这一比重增加到42.58%，中国的全球占比已经达到28.0%……
```

The join rule is geometric, not punctuation-based: **a line that starts
indented opens a paragraph; a line that stops short of the right margin closes
one** (unless it ends in `，、：（；`). Joining on punctuation fails on every
line that ends mid-clause, which is most of them.

Sanity numbers for a 418-page Chinese trade book: **11 650 lines → 2 552
paragraphs**, ~309 000 characters. If your paragraph count is close to your
line count, the rebuild did nothing.

---

## 5. Crop the book's own plates

```bash
python scripts/crop_plates.py book.pdf -o <book>-build --dpi 220
```

《缠斗》 yielded **86 caption lines → 83 plates** (figures and tables), 5.2 MB
of JPEG at q82.

The three-way test that makes this work — caption → prose boundary → measured
ink — is documented at the top of the script. The two conventions that bit:

1. **Figures are captioned BELOW, tables ABOVE.** Hard-coding either crops the
   wrong side of half the book. Propose both, let the caption's kind choose.
2. **OCR glues the label to the title.** `图1.13　1美元兑…` arrives as
   `图1.131美元兑…` and parses as figure 1.131. Assign numbers by sequence
   within a chapter; a caption whose leftover text starts with a digit cannot
   be a title.

Then **eyeball three or four crops**. Geometry cannot distinguish "plate" from
"plate plus the page header" or "plate plus the previous paragraph". On this run
the header was being swallowed on any plate that filled the top of its page, and
only the images showed it.

---

## 6. Fact packs

One `pack/<CID>.md` per chapter. What 《缠斗》's packs carried, and what each
section is for:

```markdown
# 第一章　中美经贸关系的变局与重构
- 物理页（PDF 1-based）：39–130
- 原书印刷页：21–112
- 段落数：806　　含数字的句子：348　　页脚注释：169

## 本章图表（原书）
- `fig01_01.jpg`　图1.1　2008年与2024年三大区域制造业增加值的全球占比　（第22页）

## 含数字的句子（自动抽取，引用前请回看所在页正文）
- [p21] 2008年东亚及太平洋地区……约占全球的33.94%，中国当时的全球占比为11.3%……

## 页脚注释（原书原文）
- [p21] 丁纯、张亚妮：《全球化背景下的欧洲经济：嬗变、成因与前景》……

## 正文（按原书页序）
【原书 p21】
根据世界银行WDI（世界发展指标）数据库的统计，……
```

The `## 含数字的句子` index is what makes writing fast: a writer looking for "the
manufacturing share" finds every candidate with its page, instead of re-reading
forty pages.

---

## 7. Write fragments

See `SKILL.md` stage 4 and `docs/WRITE-BRIEF` equivalents. For a scanned book
with many plates, author `.src` files and expand them:

```bash
python scripts/expand.py --frag frag --figs figs.json
```

That turns 36 `<figure>` blocks, the notes list, the quiz and the pager into one
line each, so the authored text is only prose and hand-drawn SVG.

---

## 8. Audit, and distrust a clean report

`check_all.py` must exit 0 across 1440/1024/768/430 in both palettes. Two
false-clear patterns specific to a new book:

- **A reused reader probe.** It will hard-code the previous book's ids and
  crash, and the gate will report success because it iterated over zero verdict
  lines. Generate a fresh probe: `make_reader_probe.py`.
- **A caption checker that only fails.** If every caption is "wrong", suspect
  the checker (it may not know about 表N.M, or the `· 点击可放大` suffix).

Both are in `references/pitfalls.md` group I.

---

## What the finished run looked like

| | |
|---|---|
| deliverable | **7.45 MB**, one file, offline |
| sections | 9 (cover, guide, 前言, 5 chapters, 后记) |
| original plates | **83**, all cropped from the scan, click-to-zoom |
| hand-built animated SVG charts | **35** |
| endnotes | **172**, marker ↔ item one-to-one |
| editorial components | 77 cards, 28 case boxes, 19 stat blocks, 15 comparisons, 8 number-lines, 7 quizzes |
| gate | exit 0 at four widths × two palettes; 32/32 reader checks |

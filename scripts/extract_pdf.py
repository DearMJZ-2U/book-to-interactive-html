#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract a PDF into plain chapter text, images and a TOC — same output
shape as extract_epub.py, so the rest of the pipeline does not care which
format the book arrived in.

    python extract_pdf.py <book.pdf> [-o build_dir] [--ocr] [--pages "1-40"]
    python extract_pdf.py book.pdf --toc          # just show the outline

Two cases, and you must know which one you have BEFORE planning chapters:

  digital  - page.get_text() returns real text; outlines often present.
             Figures are extractable as embedded images.
  scanned  - page.get_text() returns near-nothing. Needs OCR (--ocr), which is
             slow (~1-4 s/page) and must be run in resumable batches.
             There is NO table of contents in any machine-readable form:
             you must derive chapter page ranges by sampling pages yourself.

Traps handled (references/pitfalls.md):
  H1  a scanned book silently produces empty text without --ocr
  H2  a missing outline is not an error, it is the normal case for scans
  H3  PDF page numbers are PHYSICAL indices, not the printed page number;
      record both, or every later "page N" reference will be off
  H6  the scan check must sample the pages actually being extracted and
      judge by ratio -- probing page 1..12 misclassifies a mixed book
  H7  RapidOCR needs raw pix.samples reshaped, never PNG-encoded bytes
"""
import argparse, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        sys.exit("!! PyMuPDF not installed:  pip install pymupdf")


def parse_pages(spec, n):
    """'1-40,120,300-' -> sorted, de-duplicated, clamped 1-based list."""
    if not spec:
        return list(range(1, n + 1))
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d*)-(\d*)$", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else n
            out.update(range(max(1, a), min(n, b) + 1))
        elif part.isdigit():
            out.add(min(n, max(1, int(part))))
    return sorted(out)


def ocr_page(pix, dpi=200, limit_side=576, threads=2):
    """RapidOCR over a PyMuPDF Pixmap -> [{x0,y0,x1,y1,t}] in pixel space.

    Feed RAW samples reshaped to (h, w, channels). Passing PNG-encoded bytes
    makes numpy produce a 1-D array and RapidOCR rejects it (H7).
    """
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    global _OCR
    try:
        _OCR
    except NameError:
        _OCR = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=1)
        _OCR.text_det.limit_side_len = limit_side
        _OCR.text_det.limit_type = "min"
    n = pix.n
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, n)
    if n == 4:
        arr = arr[:, :, :3]
    elif n == 1:
        arr = np.repeat(arr, 3, axis=2)
    res, _ = _OCR(arr)
    boxes = []
    for item in res or []:
        quad, txt = item[0], item[1]
        xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
        boxes.append({"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys), "t": txt})
    boxes.sort(key=lambda z: (round(z["y0"] / 12), z["x0"]))   # reading order
    return {"dpi": dpi, "boxes": boxes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="pdf-build")
    ap.add_argument("--ocr", action="store_true",
                    help="OCR pages (required for scanned books)")
    ap.add_argument("--pages", default="", help="subset, e.g. 1-40,120")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--images", action="store_true", help="extract embedded images")
    ap.add_argument("--toc", action="store_true", help="print outline and exit")
    ap.add_argument("--force", action="store_true",
                    help="skip the scan check (mixed books: image front matter, digital body)")
    a = ap.parse_args()

    if not os.path.exists(a.pdf):
        sys.exit("no such file: " + a.pdf)
    fitz = load_fitz()
    doc = fitz.open(a.pdf)
    n = doc.page_count

    # ---- outline (digital books only) ----
    try:
        outline = doc.get_toc(simple=True)          # [[level, title, page], ...]
    except Exception:
        outline = []
    if a.toc:
        print("pages: %d\n=== outline ===" % n)
        for lvl, title, page in outline:
            print("  %s%-52s p.%d" % ("  " * (lvl - 1), title.strip()[:52], page))
        if not outline:
            print("  (none - expected for a scanned book; derive ranges yourself)")
        return 0

    wanted = parse_pages(a.pages, n)

    # ---- digital or scanned? ----
    # Sample the pages we are ACTUALLY extracting, spread across them, and
    # judge by ratio. Probing only the first pages misclassifies every book
    # with an image cover + image copyright page (H6).
    def text_ratio(pages):
        if not pages:
            return 1.0
        step = max(1, len(pages) // 12)
        sample = pages[::step][:12]
        ok = sum(1 for p in sample if len(doc[p - 1].get_text().strip()) >= 200)
        return ok / float(len(sample))

    ratio = text_ratio(wanted)
    scanned = ratio < 0.5
    if scanned and not a.ocr and not a.force:
        print("!! Only %d%% of the sampled pages have a text layer -> this looks SCANNED."
              % int(ratio * 100))
        print("!! Re-run with --ocr, or --force if only the front matter is an image.")
        return 1
    if scanned:
        print("scanned book detected (%.0f%% text coverage) -> OCR path"
              % (ratio * 100))
    elif ratio < 0.999:
        print("mixed book: %.0f%% of sampled pages have text -- OCR will fill the gaps"
              % (ratio * 100))

    out = os.path.abspath(a.out)
    txtdir, imgdir, ocrdir = (os.path.join(out, d) for d in ("text", "images", "ocr"))
    for d in (txtdir, imgdir, ocrdir):
        os.makedirs(d, exist_ok=True)

    pages, images = [], []
    for i, pno in enumerate(wanted, 1):
        page = doc[pno - 1]
        if a.ocr:
            ocr_file = os.path.join(ocrdir, "p%04d.json" % pno)
            if not os.path.exists(ocr_file):          # resumable
                pix = page.get_pixmap(dpi=a.dpi)
                json.dump(ocr_page(pix, a.dpi, threads=a.threads),
                          open(ocr_file, "w", encoding="utf-8"), ensure_ascii=False)
            d = json.load(open(ocr_file, encoding="utf-8"))
            body = "\n".join(b["t"] for b in d["boxes"])
        else:
            body = page.get_text("text")
        name = "p%04d.txt" % pno
        open(os.path.join(txtdir, name), "w", encoding="utf-8").write(body)
        pages.append({"physical": pno, "file": name, "chars": len(body.strip())})

        if a.images:
            for j, info in enumerate(page.get_images(full=True)):
                xref = info[0]
                try:
                    px = fitz.Pixmap(doc, xref)
                    if px.n - px.alpha >= 4:
                        px = fitz.Pixmap(fitz.csRGB, px)
                    fn = "p%04d_%02d.png" % (pno, j)
                    px.save(os.path.join(imgdir, fn))
                    images.append({"file": fn, "page": pno,
                                   "w": px.width, "h": px.height})
                except Exception as e:
                    print("   !! image xref %d on p.%d: %s" % (xref, pno, e))
        if i % 50 == 0:
            print("  %d/%d" % (i, len(wanted)), flush=True)

    if not pages:
        sys.exit("!! no pages extracted")
    print("pages: %d   extracted: %d" % (n, len(pages)))
    empty = [p["physical"] for p in pages if p["chars"] < 40]
    if empty:
        print("!! %d near-empty pages: %s%s" % (
            len(empty), empty[:20], " ..." if len(empty) > 20 else ""))
        if not a.ocr:
            print("!! These are likely full-page scans. Re-run with --ocr.")

    json.dump({"pages": pages, "outline": outline, "images": images,
               "scanned": scanned, "page_count": n},
              open(os.path.join(out, "pdf_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\nwrote %s/pdf_meta.json" % out)
    if outline:
        print("\nThis file DID carry an outline (%d entries). Prefer it over hand-"
              "derived ranges, and verify each page number by sampling that page:"
              % len(outline))
        for lvl, title, page in outline[:15]:
            print("    %s%s  p.%d" % ("  " * max(0, lvl - 1), title.strip()[:50], page))
        if len(outline) > 15:
            print("    ... +%d more" % (len(outline) - 15))
        print("OUTLINE PAGE NUMBERS ARE PHYSICAL (1-based, what page.get_text takes).")
    else:
        print("\nNEXT: OCR gave you page text but NO chapter boundaries.")
        print("Sample pages every ~10, find the chapter headings, then write a")
        print("RANGES table in your splitter, e.g.")
        print("    PARTS = [('ch01', '第一章　…', 1, 42), ('ch02', '第二章　…', 43, 74), ...]")
    print("Record PHYSICAL page numbers, not the printed page number - they differ")
    print("by the front matter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
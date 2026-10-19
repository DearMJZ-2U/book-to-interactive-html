#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR a scanned PDF into per-page LINES WITH GEOMETRY, then rebuild paragraphs.

    python ocr_lines.py book.pdf -o build --pages 1-418 --workers 8
    python ocr_lines.py book.pdf -o build --paragraphs     # lines.json -> paragraphs

WHY NOT JUST SORT THE BOXES

The usual recipe — sort OCR boxes by `(round(y/12), x)` and join with newlines —
gives you a *line list*, not prose. A fact pack built from it looks like this:

    （世界发展指标）数据库的统计，2008年东亚及太平洋地区（含东
    南亚）的制造业增加值约占全球的33.94%，中国当时的全球占比
    为11.3%；2024年，该地区这一比重增加到42.58%，中国的全球

Every sentence is cut at the printed line width. A writer reading that pack
cannot tell a paragraph break from a line wrap, so it either quotes half a
sentence or invents the join. This script keeps each line's LEFT and RIGHT
edges, because those two numbers are the only thing that separates a paragraph
from a wrapped line:

    new paragraph  <=>  line starts indented  (x0 > left_margin + indent)
    paragraph ends <=>  line stops short of the right margin and no comma

That is the whole trick, and it is worth its own script: on the 《缠斗》 build the
line-shredded pack produced unusable prose, while the geometry-rebuilt one read
as normal paragraphs and needed no cleanup.

TWO MORE THINGS THIS HANDLES

* Nothing is dropped. Every OCR box must appear in some line; a box that goes
  missing is a silent content loss, so the script asserts a count and exits 1.
* Page furniture (running header, folio) is separable because it is the only
  text outside the body margins — see `strip_furniture`.

RapidOCR rejects raw PNG bytes (ndim 1). Feed it raw samples, never an encoded
image.
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# One model per worker process; reopening the PDF per page is the dominant cost
# otherwise. Set to 1 thread each: the recogniser already saturates a core, and
# N processes with N threads each thrash.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

_ocr = None
_doc = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def get_doc(pdf):
    global _doc
    if _doc is None:
        import fitz
        _doc = fitz.open(pdf)
    return _doc


def page_json(out, pno):
    return os.path.join(out, "raw", "ocr", "p%04d.json" % pno)


def ocr_page(pdf, out, pno, dpi=200):
    """OCR one page. Cached, so a crash costs one page rather than the book."""
    import numpy as np
    cp = page_json(out, pno)
    if os.path.exists(cp):
        return json.load(open(cp, encoding="utf-8"))
    d = get_doc(pdf)
    pix = d[pno].get_pixmap(dpi=dpi)
    # H7: raw samples, never pix.tobytes("png")
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = arr[:, :, :3]
    res, _ = get_ocr()(arr)
    items = []
    for box, txt, score in (res or []):
        items.append({"box": [[float(p[0]), float(p[1])] for p in box],
                      "t": txt, "s": float(score)})
    rec = {"pno": pno, "dpi": dpi, "w": pix.width, "h": pix.height, "items": items}
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    tmp = cp + ".tmp"
    json.dump(rec, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, cp)
    return rec


def _worker(args):
    pdf, out, pno, dpi = args
    try:
        r = ocr_page(pdf, out, pno, dpi)
        return (pno, len(r["items"]), "")
    except Exception as e:                      # noqa: BLE001 - report, don't die
        return (pno, -1, repr(e)[:200])


# --------------------------------------------------------------------------
# boxes -> lines
# --------------------------------------------------------------------------
def band(items, tol=0.55):
    """Group boxes whose vertical centres coincide into one visual row.

    `tol` is a fraction of the MEDIAN box height, not a constant: a page with
    headings, body text and footnotes has three different type sizes, and a
    fixed pixel tolerance merges the heading into the line below it.
    """
    if not items:
        return []
    hs = sorted(b[3] - b[1] for b in items)
    med = hs[len(hs) // 2] or 10
    rows = []
    for it in sorted(items, key=lambda b: (b[1] + b[3]) / 2):
        cy = (it[1] + it[3]) / 2
        for r in rows:
            if abs(cy - r["cy"]) <= tol * med:
                r["items"].append(it)
                r["cy"] = sum((x[1] + x[3]) / 2 for x in r["items"]) / len(r["items"])
                break
        else:
            rows.append({"cy": cy, "items": [it]})
    rows.sort(key=lambda r: r["cy"])
    return rows


def to_lines(rec):
    """-> [{"t", "x0","y0","x1","y1"}] with a no-text-lost assertion."""
    items = [(it["box"][0][0], it["box"][0][1], it["box"][2][0], it["box"][3][1], it["t"])
             for it in rec["items"] if it["box"][2][0] > it["box"][0][0]]
    rows = []
    for r in band(items):
        sel = sorted(r["items"], key=lambda b: b[0])
        txt = "".join(t[4] for t in sel)
        if not txt.strip():
            continue
        rows.append({"t": txt,
                     "x0": round(min(t[0] for t in sel), 1),
                     "y0": round(min(t[1] for t in sel), 1),
                     "x1": round(max(t[2] for t in sel), 1),
                     "y1": round(max(t[3] for t in sel), 1)})
    joined = "".join(r["t"] for r in rows)
    missing = [b[4] for b in items if b[4] and b[4] not in joined]
    return rows, missing


# --------------------------------------------------------------------------
# lines -> paragraphs
# --------------------------------------------------------------------------
def cjk(s):
    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff")


def body_margin(rows):
    """The x every body line starts at: the mode of x0 among wide lines."""
    from collections import Counter
    c = Counter()
    for r in rows:
        if (r["x1"] - r["x0"]) > 0.45 * max((x["x1"] for x in rows), default=1):
            c[round(r["x0"] / 6.0) * 6] += 1
    return c.most_common(1)[0][0] if c else None


def paragraphs(rows):
    """Join lines into paragraphs using indent + short-line evidence."""
    if not rows:
        return []
    xs0 = sorted(r["x0"] for r in rows)
    xs1 = sorted(r["x1"] for r in rows)
    left = xs0[len(xs0) // 10]
    right = xs1[len(xs1) * 9 // 10]
    width = max(1.0, right - left)
    indent = 0.030 * width

    out, cur = [], []
    for r in rows:
        t = r["t"].strip()
        if not t:
            continue
        if cur and r["x0"] > left + indent:      # indented -> new paragraph
            out.append("".join(cur))
            cur = []
        cur.append(t)
        short = r["x1"] < right - 0.055 * width
        if short and not t.endswith(("，", "、", "：", "（", "；", ",", ":")):
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


def strip_furniture(rows, w, h):
    """Drop the running header and the folio.

    Both sit outside the body block: the header in the top ~8% of the page, the
    folio as a bare number at the foot. Neither belongs in the pack, and a folio
    left in place becomes a fake "number" the writer may quote as data.
    """
    keep = []
    for r in rows:
        t = r["t"].strip()
        if not t:
            continue
        if re.fullmatch(r"[\dIVXivx]{1,6}", t) and r["y0"] > 0.90 * h:
            continue                              # folio
        if r["y1"] < 0.085 * h and len(t) <= 40:
            continue                              # running header
        keep.append(r)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--paragraphs", action="store_true",
                    help="skip OCR; rebuild paragraphs from cached raw/ocr/*.json")
    a = ap.parse_args()

    os.makedirs(os.path.join(a.out, "raw", "ocr"), exist_ok=True)

    if not a.paragraphs:
        import fitz
        import multiprocessing as mp
        n = fitz.open(a.pdf).page_count
        if a.pages:
            s, e = a.pages.split("-")
            idx = list(range(int(s) - 1, int(e)))
        else:
            idx = list(range(n))
        todo = [i for i in idx if not os.path.exists(page_json(a.out, i))]
        print("pages %d | range %d | todo %d" % (n, len(idx), len(todo)), flush=True)
        if todo:
            mp.set_start_method("spawn", force=True)
            done = 0
            with mp.Pool(a.workers) as pool:
                for pno, cnt, err in pool.imap_unordered(
                        _worker, [(a.pdf, a.out, i, a.dpi) for i in todo], chunksize=1):
                    done += 1
                    if err:
                        print("  !! p%d %s" % (pno + 1, err), flush=True)
                    if done % 10 == 0 or done == len(todo):
                        print("  %d/%d" % (done, len(todo)), flush=True)

    # ---- lines.json ------------------------------------------------------
    pages, lost = [], 0
    files = sorted(f for f in os.listdir(os.path.join(a.out, "raw", "ocr"))
                   if f.endswith(".json"))
    for f in files:
        rec = json.load(open(os.path.join(a.out, "raw", "ocr", f), encoding="utf-8"))
        rows, missing = to_lines(rec)
        if missing:
            lost += len(missing)
            print("!! p%d lost %d boxes, first: %r"
                  % (rec["pno"] + 1, len(missing), missing[0][:40]))
        pages.append({"pno": rec["pno"], "w": rec.get("w"), "h": rec.get("h"), "rows": rows})
    pages.sort(key=lambda p: p["pno"])
    json.dump(pages, open(os.path.join(a.out, "raw", "lines.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("pages %d | lines %d" % (len(pages), sum(len(p["rows"]) for p in pages)))
    if lost:
        print("!! %d OCR box(es) did not survive into a line — fix before packing" % lost)
        return 1
    print("no-text-lost check: OK")

    # ---- paragraphs.txt --------------------------------------------------
    with open(os.path.join(a.out, "raw", "paragraphs.txt"), "w", encoding="utf-8") as fh:
        for p in pages:
            rows = strip_furniture(p["rows"], p.get("w") or 1000, p.get("h") or 1400)
            fh.write("\n===[[PAGE %d]]===\n" % (p["pno"] + 1))
            for para in paragraphs(rows):
                fh.write(para + "\n\n")
    print("wrote raw/paragraphs.txt — build the fact packs from THIS, not from the lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crop the book's own charts, diagrams and tables out of a scanned PDF.

    python crop_plates.py book.pdf -o build --dpi 220

Writes `build/fig/*.jpg` and `build/figs.json`:
    [{"pno", "kind", "ch", "num", "cap", "raw", "clip", "ink", "side",
      "file", "px", "bytes"}]

THE PROBLEM

`page.get_images()` finds nothing useful on a scan — every page is ONE raster,
so the "figure" you want is a rectangle inside it. The OCR boxes are the only
map of the page, and they are enough to find plates if you use them three ways:

  1. CAPTION  — a standalone line starting 图N.M / 表N.M / Fig N.M / Table N.M.
     A cross-reference in prose ("如图1.1所示") also matches, so a real caption
     is required to NOT close a parenthesis and NOT run on into a sentence.
  2. PROSE    — the nearest BODY line above (or below) the caption bounds the
     plate. This is the part that is easy to get wrong: a chart's own tick rows
     are long, wide, and start near the margin, so a naive "long line = prose"
     test puts the plate's top edge through its own axis labels.
  3. INK      — a plate is dark pixels with few words on it. Measured, not
     assumed.

WHAT ACTUALLY BIT, TWICE

* The book puts FIGURE captions BELOW the plate and TABLE captions ABOVE it.
  Hard-coding either convention silently crops the wrong side of half the book.
  Both sides are proposed and the caption's own kind decides which is preferred.
* OCR drops the gap between label and title, so "图1.13　1美元兑人民币汇率"
  arrives as "图1.131美元兑人民币汇率" and parses as figure 1.131. Numbers are
  therefore assigned by SEQUENCE within a chapter, not by trusting the split,
  and a caption whose leftover text starts with a digit cannot be a title.

A running header is the other silent contaminant: a plate that fills the top of
a page has no prose above it, so the crop starts at the page margin and swallows
"缠斗：中美经贸重构与全球经济新秩序". The header's own bottom edge bounds it.
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

LABEL = re.compile(r"^\s*([图表]|[Ff]ig(?:ure)?|[Tt]able|[Tt]ab)\s*\.?\s*"
                   r"(\d{1,2})\s*[.．\-]\s*(\d{1,3})(.*)$")

KIND = {"图": "fig", "表": "tbl", "fig": "fig", "figure": "fig",
        "table": "tbl", "tab": "tbl", "Fig": "fig", "Figure": "fig",
        "Table": "tbl", "Tab": "tbl"}

SCALE_OCR = 200 / 72.0          # OCR boxes are in 200-dpi pixels


def norm_items(rec):
    return [(it["box"][0][0], it["box"][0][1], it["box"][2][0], it["box"][3][1], it["t"])
            for it in rec["items"] if it["box"][2][0] > it["box"][0][0]]


def band(items, tol=0.55):
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


def row_text(r):
    return "".join(t[4] for t in sorted(r["items"], key=lambda b: b[0]))


def cjk(s):
    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff")


def body_margin(items, w):
    from collections import Counter
    c = Counter()
    for b in items:
        if (b[2] - b[0]) > 0.55 * w:
            c[round(b[0] / 6.0) * 6] += 1
    return c.most_common(1)[0][0] if c else None


def make_is_prose(margin, colw):
    """A BODY line: long, mostly CJK, and starting at the page's text margin.

    All three tests matter. The CJK count is what separates a paragraph from a
    table row (mostly digits) and from a chart's tick row (digits only). The
    margin test is what separates a paragraph from an axis caption that happens
    to be long. Geometry alone cannot tell a paragraph from the table grid under
    a 表N.M caption — both start at the margin and run the full column.
    """
    def is_prose(r):
        t = row_text(r)
        x0 = min(b[0] for b in r["items"])
        x1 = max(b[2] for b in r["items"])
        if cjk(t) < 12 or (x1 - x0) < 0.50 * colw:
            return False
        if margin is not None and abs(x0 - margin) > 22:
            return False
        return True
    return is_prose


def ink_ratio(pix):
    import numpy as np
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = arr[:, :, :3]
    return float((arr.mean(axis=2) < 170).mean())


def plausible_title(rest):
    """After 图N.M, does the text look like a title rather than leftover digits?"""
    if not rest:
        return False
    if rest[0].isdigit():
        # "008年…" cannot start a title; "2008年…" can
        return bool(re.match(r"(19|20)\d{2}", rest)) or \
               bool(re.match(r"\d+\s*[万亿千百]", rest))
    return True


def split_label(line):
    """Every plausible (kind, ch, num, rest) reading, longest number first."""
    m = LABEL.match(line)
    if not m:
        return []
    kind_raw, chs, digits, rest = m.group(1), m.group(2), m.group(3), m.group(4)
    kind = KIND.get(kind_raw)
    if not kind:
        return []
    out = []
    for k in range(len(digits), 0, -1):
        num, tail = digits[:k], digits[k:] + rest
        if plausible_title(tail):
            out.append((kind, int(chs), int(num), tail))
    return out


def collect(out_dir, w_default=1000):
    """Caption candidates in reading order."""
    ocr = os.path.join(out_dir, "raw", "ocr")
    found = []
    for f in sorted(os.listdir(ocr)):
        if not f.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(ocr, f), encoding="utf-8"))
        items = norm_items(rec)
        if not items:
            continue
        rows = band(items)
        w = rec.get("w") or w_default
        h = rec.get("h") or 1400
        for it in rec["items"]:
            line = it["t"].strip()
            cands = split_label(line)
            if not cands:
                continue
            if re.search(r"[。，,；;：:]", line[:30]):    # runs on into a sentence
                continue
            if len(line) > 90:
                continue
            found.append({"pno": rec["pno"], "w": w, "h": h, "items": items,
                          "rows": rows, "box_y0": it["box"][0][1],
                          "box_y1": it["box"][2][1], "line": line, "cands": cands})
    return found


def assign_numbers(found):
    """Figure numbers run 1..N inside a chapter; the sequence decides the split.

    A continuation caption ("图1.6…（续）") repeats the previous number instead
    of advancing it. Counting it as a new figure pushes every later number in
    that chapter up by one — which happened, and was only caught by eyeballing
    the crops.
    """
    expect, prev, out = {}, {}, []
    for f in found:
        kind, ch = f["cands"][0][0], f["cands"][0][1]
        want = expect.get((kind, ch), 1)
        rest_any = max(f["cands"], key=lambda t: len(t[3]))[3]

        if rest_any and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", rest_any):
            continue                      # only punctuation left -> cross-ref

        pick = None
        for k, c, num, rest in f["cands"]:
            if (k, c) == (kind, ch) and num == want:
                pick = (k, c, num, rest)
                break
        if pick is None:                  # "1" of the title glued onto the number
            for k, c, num, rest in f["cands"]:
                if (k, c) == (kind, ch) and str(num).startswith(str(want)) and num != want:
                    pick = (k, c, want, str(num)[len(str(want)):] + rest)
                    break
        if pick is None and ("（续）" in rest_any or "(续)" in rest_any) and (kind, ch) in prev:
            pick = (kind, ch, prev[(kind, ch)], rest_any)
        if pick is None:
            best = max(f["cands"], key=lambda t: len(t[3]))
            pick = (kind, ch, best[2], best[3])

        kind, ch, num, rest = pick
        expect[(kind, ch)] = num + 1
        prev[(kind, ch)] = num
        f.update(kind=kind, ch=ch, num=num, rest=rest.strip())
        out.append(f)
    return out


def crop_for(f, doc):
    """-> (clip, ink, side) for the plate this caption belongs to, or None."""
    items, rows, w, h = f["items"], f["rows"], f["w"], f["h"]
    cap_y0, cap_y1 = f["box_y0"], f["box_y1"]
    x0, x1 = 0.055 * w, 0.945 * w
    colw = x1 - x0
    is_prose = make_is_prose(body_margin(items, w), colw)

    def nearest_prose(direction):
        edge = 0.03 * h if direction == "up" else 0.97 * h
        for r in (rows if direction == "up" else reversed(rows)):
            if direction == "up" and r["cy"] >= cap_y0 - 1:
                break
            if direction == "down" and r["cy"] <= cap_y1 + 1:
                break
            if min(b[0] for b in r["items"]) >= x1 - 8:
                continue
            if max(b[2] for b in r["items"]) <= x0 + 8:
                continue
            if not is_prose(r):
                continue
            edge = (max(edge, max(b[3] for b in r["items"])) if direction == "up"
                    else min(edge, min(b[1] for b in r["items"])))
        return edge

    def header_bottom():
        bot = 0.0
        for r in rows:
            if r["cy"] > 0.085 * h:
                break
            bot = max(bot, max(b[3] for b in r["items"]))
        return bot

    def source_below():
        best = None
        for r in rows:
            if r["cy"] <= cap_y1 + 1:
                continue
            t = row_text(r)
            if re.match(r"^\s*(资料来源|数据来源|注[:：]|Source[:：]|Note[:：])", t):
                y = min(b[1] for b in r["items"])
                best = y if best is None else min(best, y)
            elif is_prose(r) and best is not None:
                break
        return best

    src_y = source_below()
    cands = []
    a, b = max(nearest_prose("up"), header_bottom()) + 2, cap_y0 - 2
    if b - a >= 0.05 * h:
        cands.append(("up", a, b))
    if src_y is not None:
        a, b = cap_y1 + 2, src_y - 2
        if b - a >= 0.04 * h:
            cands.append(("down", a, b))
    elif f["kind"] == "tbl":
        a, b = cap_y1 + 2, 0.955 * h       # table runs onto the next page
        if b - a >= 0.04 * h:
            cands.append(("down", a, b))

    # the caption's own convention decides the preference; ink breaks ties
    cands.sort(key=lambda t: 0 if t[0] == ("down" if f["kind"] == "tbl" else "up") else 1)

    best = None
    for side, a, b in cands:
        prose = 0.0
        for r in rows:
            if a <= r["cy"] <= b and is_prose(r):
                prose += (max(t[3] for t in r["items"]) - min(t[1] for t in r["items"]))
        if prose / max(1.0, b - a) > 0.22:
            continue                      # a block of prose, not a plate
        clip = [x0 / SCALE_OCR, a / SCALE_OCR, x1 / SCALE_OCR, b / SCALE_OCR]
        probe = doc[f["pno"]].get_pixmap(dpi=60, clip=clip)
        ink = ink_ratio(probe)
        if ink < 0.010:
            continue
        if (clip[3] - clip[1]) * 60.0 < 70:      # one thin line of type
            continue
        if best is None:
            best = (clip, ink, side)
        elif side == best[2] and ink > best[1]:
            best = (clip, ink, side)
        elif side == cands[0][0] and best[2] != cands[0][0]:
            best = (clip, ink, side)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--maxw", type=int, default=1240)
    ap.add_argument("--maxh", type=int, default=1600)
    ap.add_argument("--quality", type=int, default=82)
    a = ap.parse_args()

    import fitz
    import numpy as np
    from PIL import Image

    figdir = os.path.join(a.out, "fig")
    os.makedirs(figdir, exist_ok=True)
    doc = fitz.open(a.pdf)

    found = assign_numbers(collect(a.out))
    print("caption lines: %d" % len(found))

    made, skipped = [], []
    for f in found:
        r = crop_for(f, doc)
        if not r:
            skipped.append(f)
            continue
        clip, ink, side = r
        name = "%s%02d_%02d.jpg" % (f["kind"], f["ch"], f["num"])
        pix = doc[f["pno"]].get_pixmap(dpi=a.dpi, clip=clip)
        img = Image.frombytes("RGB", (pix.width, pix.height),
                              pix.samples[:pix.width * pix.height * 3])
        # trim the surrounding paper so the plate fills its frame
        arr = np.array(img.convert("L"))
        ys, xs = np.where(arr < 210)
        if len(ys):
            pad = 6
            img = img.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                            min(img.width, xs.max() + pad), min(img.height, ys.max() + pad)))
        if img.width > a.maxw:
            img = img.resize((a.maxw, max(1, round(img.height * a.maxw / img.width))),
                             Image.LANCZOS)
        if img.height > a.maxh:
            img = img.resize((max(1, round(img.width * a.maxh / img.height)), a.maxh),
                             Image.LANCZOS)
        path = os.path.join(figdir, name)
        # JPEG q82 keeps a zoomed plate readable and the whole book near 10 MB;
        # a PNG of a page-sized scan costs ~730 kB per plate.
        img.save(path, "JPEG", quality=a.quality, optimize=True, progressive=True)
        made.append(dict(pno=f["pno"], kind=f["kind"], ch=f["ch"], num=f["num"],
                         cap=("%s%d.%d　%s" % ("图" if f["kind"] == "fig" else "表",
                                               f["ch"], f["num"], f["rest"]))[:90],
                         raw=f["line"], clip=clip, ink=round(ink, 4), side=side,
                         file=name, px=list(img.size), bytes=os.path.getsize(path)))

    doc.close()
    json.dump(made, open(os.path.join(a.out, "figs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("plates written: %d | skipped: %d | %.2f MB"
          % (len(made), len(skipped), sum(x["bytes"] for x in made) / 1048576))
    for r in made:
        print("  %-13s p%-4d %4dx%-4d %-4s ink=%.3f %s"
              % (r["file"], r["pno"] + 1, r["px"][0], r["px"][1], r["side"],
                 r["ink"], r["cap"][:46]))
    if skipped:
        print("\n--- skipped (no clean plate found) ---")
        for f in skipped:
            print("  p%-4d %s" % (f["pno"] + 1, f["line"][:64]))
    print("\nEYEBALL A SAMPLE. Geometry cannot tell a crop that includes the "
          "page header or the previous paragraph from a correct one; three or "
          "four spot checks catch what the numbers cannot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

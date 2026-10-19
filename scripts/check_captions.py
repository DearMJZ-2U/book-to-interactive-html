#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify every figure caption quotes a caption the book actually printed.

    python check_captions.py --frag frag --figs figs.json [--sections sections.py]

Two things are forbidden, and this script enforces both:

  1. A caption may not DESCRIBE the plate. There is no image input in this
     pipeline, so any sentence about what the picture shows is invented. A
     vocabulary test catches the usual tells (画面/图中/可以看到/描绘…).
  2. A quoted caption must match one in figs.json, keyed by 图<ch>.<n> or
     表<ch>.<n>, with identical wording after normalisation. That is what makes
     the plate traceable to the page it was cropped from.

THREE BUGS THIS SCRIPT SHIPPED WITH, ALL OF WHICH REPORTED FALSE FAILURES

  a. Matching only `图N.M` made every TABLE caption look like it "quotes no
     figure number" — this book labels tables 表N.M.
  b. Comparing the whole caption against the source failed on every single one,
     because the house form appends " · 点击可放大" for the reader. That is
     chrome, not caption text, and must be stripped before the comparison.
  c. Requiring a 图N.M on an unnumbered plate rejected legitimate plates that
     carry no printed number. Only plates that HAVE a number must quote it.

A check that can only ever fail is as useless as one that can only ever pass.
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

LABELS = ("原书插图", "原书扉页", "原书封面", "出版社标志", "原书图版", "原书图表")

DESCRIBE = re.compile(
    r"(画面|图中|圖中|可以看到|可見到|描绘|描繪|显示|顯示|照片中|插图里|插圖裡"
    r"|画中|畫中|站着|站著|坐着一|坐著一|手里拿|手裡拿|身穿|脸上|臉上"
    r"|一只|一隻|一头|一頭|两个人|兩個人|这张图|這張圖|图上|圖上)")

FIGRE = r'<figure class="(?:fig|plate)"[^>]*>'

# Both plate kinds carry a printed number in this book.
CAPNUM = re.compile(r"([图表])\s*(\d{1,2})\s*[.．]\s*(\d{1,3})")

# The click-to-zoom hint the reader sees. Chrome, not caption text.
ZOOM_HINT = re.compile(r"\s*[·・]\s*点击可放大\s*$")


def norm(s):
    s = re.sub(r"\s+", "", s)
    return s.replace("（", "(").replace("）", ")").replace("，", ",")


def load_captions(figs_path):
    out = {}
    if not os.path.exists(figs_path):
        return out
    for f in json.load(open(figs_path, encoding="utf-8")):
        cap = f.get("cap") or ""
        m = CAPNUM.match(cap)
        if m:
            out["%s%s.%s" % (m.group(1), m.group(2), m.group(3))] = \
                norm(CAPNUM.sub("", cap))
    return out


def split_caption(fc):
    lab = re.search(r"<b>(.*?)</b>", fc, re.S)
    src = re.search(r"(?s)<span class=\"src\">(.*?)</span>", fc)
    txt = re.sub(r"(?s)<span class=\"src\">.*?</span>", " ", fc)
    txt = re.sub(r"<[^>]+>", "", txt).replace("&nbsp;", " ")
    txt = re.sub(r"[　\s·・]+", " ", txt).strip()
    return (re.sub(r"<[^>]+>", "", lab.group(1)).strip() if lab else "",
            re.sub(r"<[^>]+>", "", src.group(1)).strip() if src else "",
            txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frag", default="frag")
    ap.add_argument("--figs", default="figs.json")
    ap.add_argument("--sections", default=None,
                    help="optional sections.py; when given, per-section image "
                         "counts are compared against it")
    a = ap.parse_args()

    known = load_captions(a.figs)
    print("captions in %s: %d" % (a.figs, len(known)))

    wanted = None
    if a.sections:
        sys.path.insert(0, os.path.dirname(os.path.abspath(a.sections)))
        import importlib.util
        spec = importlib.util.spec_from_file_location("sections", a.sections)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        wanted = {s[0]: s[5] for s in mod.SECTIONS}

    bad, total = 0, 0
    print("%-8s %4s %4s  %s" % ("cid", "fig", "cap", "verdict"))
    for f in sorted(os.listdir(a.frag)):
        if not f.endswith(".html"):
            continue
        cid = f[:-5]
        s = open(os.path.join(a.frag, f), encoding="utf-8").read()
        figs = re.findall(FIGRE + r"(.*?)</figure>", s, re.S)
        caps = re.findall(r"<figcaption>(.*?)</figcaption>", s, re.S)
        errs = []

        if wanted is not None and cid in wanted:
            if len(figs) != len(wanted[cid]):
                errs.append("%d <figure> != %d declared"
                            % (len(figs), len(wanted[cid])))
        if len(caps) != len(figs):
            errs.append("%d figcaption for %d figure" % (len(caps), len(figs)))

        for n, fc in enumerate(caps, 1):
            lab, quoted, txt = split_caption(fc)
            total += 1
            if lab not in LABELS:
                errs.append("caption %d label %r not in %s"
                            % (n, lab, "/".join(LABELS)))
            said = ZOOM_HINT.sub("", quoted or txt)
            m = CAPNUM.search(said)
            if not m:
                errs.append("caption %d quotes no 图N.M / 表N.M" % n)
            else:
                key = "%s%s.%s" % (m.group(1), m.group(2), m.group(3))
                if key not in known:
                    errs.append("caption %d quotes %s, not a plate in figs.json"
                                % (n, key))
                elif norm(CAPNUM.sub("", said)) != known[key]:
                    errs.append("caption %d quotes %s as %r but the source reads %r"
                                % (n, key, norm(CAPNUM.sub("", said))[:34],
                                   known[key][:34]))
            for field, where in ((lab, "label"), (txt, "text"), (quoted, "quote")):
                mm = DESCRIBE.search(field)
                if mm:
                    errs.append("caption %d %s describes picture content (%s)"
                                % (n, where, mm.group(0)))

        # alt text carries the same duty: a screen reader reads it aloud
        for n, al in enumerate(re.findall(r'<img[^>]*\balt="([^"]*)"', s), 1):
            mm = DESCRIBE.search(al)
            if mm:
                errs.append("alt %d describes picture content (%s)" % (n, mm.group(0)))

        for n, fg in enumerate(figs, 1):
            if "<img" not in fg:
                errs.append("figure %d has no <img>" % n)
            if 'class="src"' not in fg:
                errs.append("figure %d has no src span" % n)

        bad += len(errs)
        if figs or errs:
            print("%-8s %4d %4d  %s" % (cid, len(figs), len(caps),
                                        "OK" if not errs else " | ".join(errs)))

    print("\ncaptions checked: %d" % total)
    print("non-source captions: %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

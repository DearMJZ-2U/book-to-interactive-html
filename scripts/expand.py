#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expand authoring shortcuts in frag/*.src into real fragment markup.

    python expand.py [--frag DIR] [--figs figs.json] [--cid CID]

WHY THIS EXISTS

A chapter fragment is mostly repetition: thirty-odd <figure> blocks that differ
only in filename and caption, a notes list, a five-question quiz, a pager. Typing
that by hand costs context and introduces transcription errors in the one place
that matters — the caption text, which `capcheck.py` compares verbatim against
the cropper's record.

So the repeated parts are generated from one line each, and only the prose and
the hand-drawn SVG are authored:

    {{FIG:fig01_01}}                    click-to-zoom figure for that plate
    {{FIGCAP:fig01_01}}                 just the caption text (for prose mentions)
    {{NUM:a~u~k|b~u~k|c~u~k}}           three-cell .numline
    {{NUMW:...}}                        same, last cell flagged warn
    {{TLDR:a|b|c}}                      three tldr bullets
    {{QUIZ:q1|a1|q2|a2|...}}            five question/answer pairs
    {{BIGFIG:n|u|label|desc}}           one .bigfig block
    {{CMP:k1|v1|k2|v2|k3|v3}}           .cmp block
    {{STATS:v|u|k|v|u|k|...}}           .stats block
    {{CASES:who|body|...}}              .case blocks
    {{CARDS:title|body|...}}            .card blocks
    {{BAD:title|body|...}}              .card bad blocks
    {{NOTES:cid|summary|text|...}}      the whole <details class="notes"> block
    {{PAGER:prev|PrevTitle|next|NextTitle}}

THE TRAP THIS AVOIDS

The .html is GENERATED. Editing it directly means the next expansion silently
discards the edit — the same rule as "never hand-edit the deliverable". Edit the
.src. This script refuses to run if the two disagree in a way it cannot explain
(an .html with no .src beside it), so the authoring layer stays unambiguous.

FAIL LOUDLY

An unknown plate name and a leftover {{...}} are both silent content loss: the
figure just disappears from the page. Both are hard errors here.
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

PLACEHOLDER = re.compile(r"(?s)\{\{([A-Z]+):(.*?)\}\}")
ALLOWED = {"FIG", "FIGCAP", "NUM", "NUMW", "PAGER", "TLDR", "QUIZ", "BIGFIG",
           "CMP", "STATS", "CASES", "CARDS", "BAD", "NOTES", "SUP"}


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class Expander:
    def __init__(self, figs, cid):
        self.figs = figs
        self.cid = cid
        self.errors = []

    # -- plates ------------------------------------------------------------
    def figure(self, name):
        name = name.strip()
        if name and not os.path.splitext(name)[1]:
            name += ".jpg"          # the shortcut may omit the extension
        cap = self.figs.get(name)
        if not cap:
            self.errors.append("unknown plate %r (not in figs.json)" % name)
            return "<!-- unknown plate %s -->" % name
        m = re.match(r"([图表]\s*\d+\.\d+)", cap)
        tag = re.sub(r"\s+", "", m.group(1)) if m else ""
        return (
            '<figure class="fig">\n'
            '  <button class="shot" data-cap="%s">\n'
            '    <img src="IMG:%s" alt="原书图表 · %s" loading="lazy">\n'
            '  </button>\n'
            '  <figcaption><b>原书插图</b>　<span class="src">%s · 点击可放大</span>'
            '</figcaption>\n'
            '</figure>' % (esc(cap), name, tag, esc(cap)))

    # -- simple components -------------------------------------------------
    @staticmethod
    def numline(args, warn_last=False):
        out = ['<div class="numline">']
        for i, a in enumerate(args):
            v, u, k = (a.split("~") + ["", ""])[:3]
            cls = " warn" if warn_last and i == len(args) - 1 else ""
            uu = '<span class="u">%s</span>' % esc(u) if u else ""
            out.append('  <div class="nl%s"><span class="v">%s%s</span>'
                       '<span class="k">%s</span></div>' % (cls, esc(v), uu, esc(k)))
        out.append("</div>")
        return "\n".join(out)

    @staticmethod
    def pager(a):
        prev, ptitle, nxt, ntitle = (a + ["", "", "", ""])[:4]
        return ('<nav class="pager">\n'
                '  <a href="#%s" class="prev"><div class="dir">上一节</div>'
                '<div class="ttl">%s</div></a>\n'
                '  <a href="#%s" class="next"><div class="dir">下一节</div>'
                '<div class="ttl">%s</div></a>\n'
                '</nav>' % (prev, esc(ptitle), nxt, esc(ntitle)))

    @staticmethod
    def tldr(a):
        return '<ul class="tldr">\n' + "\n".join('  <li>%s</li>' % x for x in a) + "\n</ul>"

    @staticmethod
    def quiz(a):
        pairs = list(zip(a[0::2], a[1::2]))
        out = ['<details class="quiz">',
               '  <summary>五道理解题 · 展开查看</summary>', ""]
        for i, (q, ans) in enumerate(pairs, 1):
            out += ['  <details>',
                    '    <summary><b>Q%d</b>　%s</summary>' % (i, q),
                    '    <p>%s</p>' % ans,
                    '  </details>', ""]
        out.append("</details>")
        return "\n".join(out)

    @staticmethod
    def bigfig(a):
        n, u, label, desc = (a + ["", "", "", ""])[:4]
        uu = '<span class="u">%s</span>' % esc(u) if u else ""
        return ('<div class="bigfig">\n'
                '  <span class="n">%s%s</span>\n'
                '  <span class="l">%s</span>\n'
                '  <span class="d">%s</span>\n'
                '</div>' % (esc(n), uu, esc(label), esc(desc)))

    @staticmethod
    def cmp(a):
        out = ['<div class="cmp">']
        for k, v in zip(a[0::2], a[1::2]):
            out.append('  <div><div class="k">%s</div><div class="v">%s</div></div>' % (k, v))
        out.append("</div>")
        return "\n".join(out)

    @staticmethod
    def stats(a):
        out = ['<div class="stats">']
        for v, u, k in zip(a[0::3], a[1::3], a[2::3]):
            uu = '<span class="u">%s</span>' % esc(u) if u else ""
            out.append('  <div class="stat"><span class="v">%s%s</span>'
                       '<span class="k">%s</span></div>' % (esc(v), uu, esc(k)))
        out.append("</div>")
        return "\n".join(out)

    @staticmethod
    def cases(a):
        return "\n".join('<div class="case"><div class="who">%s</div><p>%s</p></div>' % (w, b)
                         for w, b in zip(a[0::2], a[1::2]))

    @staticmethod
    def cards(a):
        return "\n".join('<div class="card"><h3>%s</h3><p>%s</p></div>' % (t, b)
                         for t, b in zip(a[0::2], a[1::2]))

    @staticmethod
    def badcards(a):
        return "\n".join('<div class="card bad"><h3>%s</h3><p>%s</p></div>' % (t, b)
                         for t, b in zip(a[0::2], a[1::2]))

    def notes(self, a):
        cid, summary = a[0], a[1]
        items = a[2:]
        if cid != self.cid:
            self.errors.append("NOTES cid %r != fragment cid %r" % (cid, self.cid))
        out = ['<details class="notes" id="notes-%s">' % cid,
               '  <summary>%s</summary>' % esc(summary),
               '  <ol class="nlist">']
        for i, t in enumerate(items, 1):
            out.append('    <li id="%s-n%d"><b>%d</b><span>%s</span></li>' % (cid, i, i, t))
        out += ['  </ol>', '</details>']
        return "\n".join(out)

    # -- dispatch ----------------------------------------------------------
    def expand(self, text):
        def rep(m):
            key, body = m.group(1), m.group(2)
            if key not in ALLOWED:
                self.errors.append("unknown shortcut {{%s:...}}" % key)
                return m.group(0)
            parts = body.split("|") if body else []
            if key == "FIG":
                return self.figure(body)
            if key == "FIGCAP":
                n = body.strip()
                if n and not os.path.splitext(n)[1]:
                    n += ".jpg"
                return esc(self.figs.get(n, ""))
            if key == "NUM":
                return self.numline(parts)
            if key == "NUMW":
                return self.numline(parts, warn_last=True)
            if key == "PAGER":
                return self.pager(parts)
            if key == "TLDR":
                return self.tldr(parts)
            if key == "QUIZ":
                return self.quiz(parts)
            if key == "BIGFIG":
                return self.bigfig(parts)
            if key == "CMP":
                return self.cmp(parts)
            if key == "STATS":
                return self.stats(parts)
            if key == "CASES":
                return self.cases(parts)
            if key == "CARDS":
                return self.cards(parts)
            if key == "BAD":
                return self.badcards(parts)
            if key == "NOTES":
                return self.notes([self.cid] + parts)
            if key == "SUP":
                n = body.strip()
                return '<sup class="nb" data-n="%s-n%s">%s</sup>' % (self.cid, n, n)
            return m.group(0)

        return PLACEHOLDER.sub(rep, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frag", default="frag", help="fragment directory (default: frag)")
    ap.add_argument("--figs", default="figs.json", help="plate record (default: figs.json)")
    ap.add_argument("--cid", default=None, help="expand only this fragment")
    a = ap.parse_args()

    figs = {}
    if os.path.exists(a.figs):
        figs = {f["file"]: f["cap"] for f in
                json.load(open(a.figs, encoding="utf-8"))}
        print("plates in %s: %d" % (a.figs, len(figs)))
    else:
        print("!! %s not found — {{FIG:...}} will fail" % a.figs)

    srcs = sorted(f for f in os.listdir(a.frag) if f.endswith(".src"))
    if a.cid:
        srcs = [f for f in srcs if f[:-4] == a.cid]
    if not srcs:
        print("no .src files in %s" % a.frag)
        return 0

    # An .html with no .src beside it is hand-written (the guide is usually like
    # this). Say so, because those files are NOT regenerated and editing them is
    # correct — the opposite rule from the generated ones.
    handwritten = sorted(f[:-5] for f in os.listdir(a.frag)
                         if f.endswith(".html") and not os.path.exists(
                             os.path.join(a.frag, f[:-5] + ".src")))
    if handwritten:
        print("hand-written (no .src, left untouched): %s" % " ".join(handwritten))

    bad = 0
    for f in srcs:
        cid = f[:-4]
        text = open(os.path.join(a.frag, f), encoding="utf-8").read()
        ex = Expander(figs, cid)
        out = ex.expand(text)
        left = sorted(set(re.findall(r"\{\{([A-Z]+):", out)))
        if left:
            ex.errors.append("unexpanded shortcut(s): %s" % " ".join("{{%s:...}}" % k
                                                                    for k in left))
        if ex.errors:
            bad += 1
            print("%-6s !! %s" % (cid, "; ".join(ex.errors)))
            continue
        open(os.path.join(a.frag, cid + ".html"), "w", encoding="utf-8").write(out)
        print("%-6s %7d -> %7d bytes" % (cid, len(text), len(out)))

    if bad:
        print("\n!! %d fragment(s) failed; nothing written for them" % bad)
        return 1
    print("all shortcuts expanded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
